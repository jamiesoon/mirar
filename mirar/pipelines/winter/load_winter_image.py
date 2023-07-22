"""
Module for loading raw WINTER images and ensuring they have the correct format
"""
import logging
import os
import warnings
from pathlib import Path

import astropy
import numpy as np
from astropy.io import fits
from astropy.stats import sigma_clipped_stats
from astropy.time import Time
from astropy.utils.exceptions import AstropyWarning

from mirar.data import Image
from mirar.io import open_fits, open_mef_fits, open_mef_image, open_raw_image
from mirar.paths import (
    BASE_NAME_KEY,
    COADD_KEY,
    GAIN_KEY,
    OBSCLASS_KEY,
    PROC_FAIL_KEY,
    PROC_HISTORY_KEY,
    RAW_IMG_KEY,
)
from mirar.pipelines.winter.constants import (
    imgtype_dict,
    palomar_observer,
    subdets,
    winter_filters_map,
)
from mirar.pipelines.winter.models import DEFAULT_FIELD, default_program, itid_dict

logger = logging.getLogger(__name__)


def clean_header(header: fits.Header) -> fits.Header:
    """
    Function to clean the header of an image, adding in missing keys and
    correcting values where necessary

    :param header: Header to clean
    :return: Updated header
    """
    header[GAIN_KEY] = 1.0
    header["UTCTIME"] = Time(header["UTCISO"], format="iso").isot

    date_t = Time(header["UTCTIME"])

    header["MJD-OBS"] = date_t.mjd
    header["DATE-OBS"] = date_t.isot

    header[OBSCLASS_KEY] = ["science", "calibration"][
        header["OBSTYPE"] in ["DARK", "FLAT"]
    ]

    if header["OBSTYPE"] == "DARK":
        sun_pos = palomar_observer.sun_altaz(Time(header["UTCTIME"]))
        if sun_pos.alt.to_value("deg") > -25.0:
            header[OBSCLASS_KEY] = "TEST"
            header["OBSTYPE"] = "TEST"

    header["EXPTIME"] = np.rint(header["EXPTIME"])

    header["TARGET"] = header["OBSTYPE"].lower()

    if header["TARGNAME"] == "":
        header["TARGNAME"] = f"field_{header['FIELDID']}"

    if (header["FILTERID"] == "dark") & (header["OBSTYPE"] != "BIAS"):
        header["OBSTYPE"] = "DARK"
        header["TARGET"] = "dark"

    header["RA"] = header["RADEG"]
    header["DEC"] = header["DECDEG"]

    obstime = Time(header["UTCTIME"])
    header["EXPID"] = int((obstime.mjd - 59000.0) * 86400.0)  # seconds since 60000 MJD

    if COADD_KEY not in header.keys():
        logger.debug(f"No {COADD_KEY} entry. Setting coadds to 1.")
        header[COADD_KEY] = 1

    header[PROC_HISTORY_KEY] = ""
    header[PROC_FAIL_KEY] = False

    filter_dict = {"J": 1, "H": 2, "Ks": 3}

    if "FILTERID" not in header.keys():
        header["FILTERID"] = filter_dict[header["FILTER"]]
    if "FIELDID" not in header.keys():
        header["FIELDID"] = 99999
    if "PROGPI" not in header.keys():
        header["PROGPI"] = "Kasliwal"
    if "PROGID" not in header.keys():
        header["PROGID"] = 0

    if "CTYPE1" not in header:
        header["CTYPE1"] = "RA---TAN"
    if "CTYPE2" not in header:
        header["CTYPE2"] = "DEC--TAN"

    header["FILTER"] = header["FILTERID"]
    if header["FILTER"] == "Hs":
        header["FILTER"] = "H"

    header["FID"] = int(winter_filters_map[header["FILTERID"]])

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", AstropyWarning)
        header["NIGHTDATE"] = obstime.to_datetime().strftime("%Y-%m-%d")

    header["IMGTYPE"] = header["OBSTYPE"]

    if not header["IMGTYPE"] in imgtype_dict:
        header["ITID"] = itid_dict[imgtype_dict["OTHER"]]
    else:
        header["ITID"] = itid_dict[imgtype_dict[header["OBSTYPE"]]]

    header["EXPMJD"] = header["MJD-OBS"]

    for key in ["MOONRA", "MOONDEC", "MOONILLF", "MOONPHAS", "SUNAZ"]:
        if header[key] == "":
            header[key] = 99

    if header["FIELDID"] < 0:
        header["FIELDID"] = DEFAULT_FIELD

    # If PROGNAME is not present or is empty, set it to default here.
    # Otherwise, it gets set to default in the insert_entry for exposures.
    if "PROGNAME" not in header:
        header["PROGNAME"] = default_program.progname

    if header["PROGNAME"] == "":
        header["PROGNAME"] = default_program.progname

    return header


def load_proc_winter_image(path: str | Path) -> tuple[np.array, fits.Header]:
    """
    Load proc image
    """
    logger.debug(f"Loading {path}")
    data, header = open_fits(path)
    if "weight" in path:
        header["OBSTYPE"] = "weight"

    header["FILTER"] = header["FILTERID"]

    return data, header


def load_stacked_winter_image(
    path: str | Path,
) -> tuple[np.array, fits.Header]:
    """
    Load proc image
    """
    logger.debug(f"Loading {path}")
    data, header = open_fits(path)

    if "weight" in path:
        header["OBSTYPE"] = "weight"

        header["OBSCLASS"] = "weight"
        header["COADDS"] = 1
        header["TARGET"] = "science"
        header["CALSTEPS"] = ""
        header["PROCFAIL"] = 1
        header["RAWPATH"] = ""
        header["BASENAME"] = os.path.basename(path)
        header["TARGNAME"] = "weight"
    if "UTCTIME" not in header.keys():
        header["UTCTIME"] = "2023-06-14T00:00:00"

    return data, header


def load_test_winter_image(
    path: str | Path,
) -> Image:
    image = open_raw_image(path)
    header = clean_header(image.header)
    image.set_header(header)
    return image


def load_raw_winter_mef(
    path: str | Path,
) -> tuple[astropy.io.fits.Header, list[np.array], list[astropy.io.fits.Header]]:
    """
    Load mef image.
    """
    header, split_data, split_headers = open_mef_fits(path)

    header = clean_header(header)

    header[BASE_NAME_KEY] = os.path.basename(path)
    header[RAW_IMG_KEY] = path

    # Sometimes there are exptime keys
    for board_header in split_headers:
        if "EXPTIME" in board_header.keys():
            del board_header["EXPTIME"]

    return header, split_data, split_headers


def load_winter_mef_image(
    path: str | Path,
) -> list[Image]:
    """
    Function to load iwinter mef images

    :param path: Path to image
    :return: list of images
    """
    return open_mef_image(path, load_raw_winter_mef, extension_key="BOARD_ID")


def annotate_winter_subdet_headers(image: Image) -> Image:
    """
    Annotate winter header with information on the subdetector

    :param image: Image to annotate
    :return: Annotated header
    """
    data = image.get_data()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", AstropyWarning)
        _, med, std = sigma_clipped_stats(data, sigma=3.0, maxiters=5)
        image["MEDCOUNT"] = med
        image["STDDEV"] = std
        image["PROCSTATUS"] = 0

    subnx, subny, subnxtot, subnytot = (
        image["SUBNX"],
        image["SUBNY"],
        image["SUBNXTOT"],
        image["SUBNYTOT"],
    )

    mask = (
        (subdets["nx"] == subnx)
        & (subdets["ny"] == subny)
        & (subdets["nxtot"] == subnxtot)
        & (subdets["nytot"] == subnytot)
        & (subdets["boardid"] == image["BOARD_ID"])
    )
    assert np.sum(mask) == 1, (
        f"Subdet not found for nx={subnx}, ny={subny}, "
        f"nxtot={subnxtot}, nytot={subnytot} and boardid={image['BOARD_ID']}"
    )
    image["SUBDETID"] = int(subdets[mask]["subdetid"].iloc[0])
    image["RAWID"] = int(f"{image['EXPID']}_{str(image['SUBDETID']).rjust(2, '0')}")
    image["USTACKID"] = None

    if "DATASEC" in image.keys():
        del image["DATASEC"]

    return image


def get_raw_winter_mask(image: Image) -> np.ndarray:
    """
    Get mask for raw winter image.
    """
    data = image.get_data()
    header = image.header

    mask = np.zeros(data.shape)
    if header["BOARD_ID"] == 0:
        # data[:500, 700:1500] = np.nan
        mask[1075:, :] = 1.0
        mask[:, 1950:] = 1.0
        mask[:20, :] = 1.0

    if header["BOARD_ID"] == 1:
        pass

    if header["BOARD_ID"] == 2:
        mask[1060:, :] = 1.0
        mask[:, 1970:] = 1.0
        mask[:55, :] = 1.0
        mask[:, :20] = 1.0

    if header["BOARD_ID"] == 3:
        mask[1085:, :] = 1.0
        mask[:, 1970:] = 1.0
        mask[:55, :] = 1.0
        mask[:, :20] = 1.0

    if header["BOARD_ID"] == 4:
        # data[610:, :280] = np.nan
        mask[:, 1948:] = 1.0
        mask[:, :61] = 1.0
        mask[:20, :] = 1.0
        mask[1060:, :] = 1.0
        mask[:, 999:1002] = 1.0

    if header["BOARD_ID"] == 5:
        # data[740:, 1270: 1850] = np.nan
        mask[1072:, :] = 1.0
        mask[:, 1940:] = 1.0
        mask[:15, :] = 1.0
        mask[680:, 1180:] = 1.0

    return mask.astype(bool)
