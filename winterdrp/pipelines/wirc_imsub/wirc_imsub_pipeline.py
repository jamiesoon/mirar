from winterdrp.pipelines.base_pipeline import Pipeline
from winterdrp.references.wirc import WIRCRef
from winterdrp.processors.astromatic.swarp.swarp import Swarp
from winterdrp.processors.astromatic.sextractor.sextractor import Sextractor
from winterdrp.processors.astromatic.psfex import PSFex
from winterdrp.processors.reference import Reference
from winterdrp.processors.zogy.zogy import ZOGY, ZOGYPrepare
from winterdrp.processors.candidates.candidate_detector import DetectCandidates
import numpy as np
from astropy.io import fits, ascii
import os
from astropy.time import Time
import logging

from winterdrp.processors.alert_packets.avro_alert import AvroPacketMaker
from winterdrp.processors.utils.image_loader import ImageLoader
from winterdrp.processors.utils.image_selector import ImageSelector, ImageBatcher
from winterdrp.paths import core_fields, base_name_key
from winterdrp.processors.candidates.utils import RegionsWriter, DataframeWriter
from winterdrp.processors.photometry.psf_photometry import PSFPhotometry
from penquins import Kowalski
from winterdrp.catalog.kowalski import TMASS, PS1
from winterdrp.processors.xmatch import XMatch

logger = logging.getLogger(__name__)


def wirc_reference_image_generator(
        header: fits.header,
        images_directory: str = os.environ.get('REF_IMG_DIR'),
):
    object_name = header['OBJECT']
    filter_name = header['FILTER']
    return WIRCRef(
        object_name=object_name,
        filter_name=filter_name,
        images_directory_path=images_directory
    )


def wirc_reference_image_resampler(pixscale,
                                   x_imgpixsize,
                                   y_imgpixsize,
                                   center_ra,
                                   center_dec,
                                   propogate_headerlist,
                                   temp_output_sub_dir,
                                   night_sub_dir,
                                   include_scamp,
                                   combine,
                                   gain,
                                   subtract_bkg):
    logger.debug(f'Night sub dir is {night_sub_dir}')
    return Swarp(swarp_config_path='~/wirc_imsub/config/config.swarp',
                 pixscale=pixscale,
                 x_imgpixsize=x_imgpixsize,
                 y_imgpixsize=y_imgpixsize,
                 center_ra=center_ra,
                 center_dec=center_dec,
                 propogate_headerlist=propogate_headerlist,
                 temp_output_sub_dir=temp_output_sub_dir,
                 night_sub_dir=night_sub_dir,
                 include_scamp=include_scamp,
                 combine=combine,
                 gain=gain,
                 cache=True,
                 subtract_bkg=subtract_bkg
                 )


def wirc_reference_sextractor(output_sub_dir, gain):
    return Sextractor(config_path='winterdrp/pipelines/wirc_imsub/config/photomCat.sex',
                      parameter_path='winterdrp/pipelines/wirc_imsub/config/photom.param',
                      filter_path='winterdrp/pipelines/wirc_imsub/config/default.conv',
                      starnnw_path='winterdrp/pipelines/wirc_imsub/config/default.nnw',
                      gain=gain,
                      output_sub_dir=output_sub_dir,
                      cache=True
                      )


def wirc_reference_psfex(output_sub_dir, norm_fits):
    return PSFex(config_path='winterdrp/pipelines/wirc_imsub/config/photom.psfex',
                 output_sub_dir=output_sub_dir,
                 norm_fits=norm_fits,
                 cache=True
                 )


def detect_candidates_sextractor():
    pass


def get_kowalski():
    # secrets = ascii.read('/Users/viraj/ztf_utils/secrets.csv', format='csv')
    username_kowalski = os.environ.get('kowalski_user')
    password_kowalski = os.environ.get('kowalski_pwd')
    if username_kowalski is None:
        err = 'Kowalski username not provided, please run export kowalski_user=<user>'
        logger.error(err)
        raise ValueError
    if password_kowalski is None:
        err = 'Kowalski password not provided, please run export KOWALSKI_PWD=<user>'
        logger.error(err)
        raise ValueError
    protocol, host, port = "https", "kowalski.caltech.edu", 443
    k = Kowalski(username=username_kowalski, password=password_kowalski, protocol=protocol, host=host, port=port)
    connection_ok = k.ping()
    logger.info(f'Connection OK: {connection_ok}')
    return k


def load_raw_wirc_image(
        path: str
) -> tuple[np.array, fits.Header]:
    with fits.open(path) as img:
        data = img[0].data
        header = img[0].header
        header["FILTER"] = header["AFT"].split("__")[0]
        header["OBSCLASS"] = ["calibration", "science"][header["OBSTYPE"] == "object"]
        header["CALSTEPS"] = ""
        header["BASENAME"] = os.path.basename(path)
        logger.info(header["BASENAME"])
        header["TARGET"] = header["OBJECT"].lower()
        header["UTCTIME"] = header["UTSHUT"]
        header["MJD-OBS"] = Time(header['UTSHUT']).mjd
        # header.append(('GAIN', self.gain, 'Gain in electrons / ADU'), end=True)
        # header = self.set_saturation(header)
        if not 'COADDS' in header.keys():
            logger.debug('Setting COADDS to 1')
            header['COADDS'] = 1
        if not 'CALSTEPS' in header.keys():
            logger.debug('Setting CALSTEPS to blank')
            header['CALSTEPS'] = ''

        data[data == 0] = np.nan
    return data, header


class WircImsubPipeline(Pipeline):
    name = "wirc_imsub"

    header_keys = [
        "UTSHUT",
        'OBJECT',
        "FILTER",
        "EXPTIME"
    ]
    batch_split_keys = ["UTSHUT"]

    pipeline_configurations = {
        None: [
            ImageLoader(
                input_sub_dir="raw",
                load_image=load_raw_wirc_image
            ),
            # ImageBatcher(split_key='UTSHUT'),
            ImageSelector((base_name_key, "ZTF21aagppzg_J_stack_1_20210330.fits")),
            Reference(
                ref_image_generator=wirc_reference_image_generator,
                ref_swarp_resampler=wirc_reference_image_resampler,
                ref_sextractor=wirc_reference_sextractor,
                ref_psfex=wirc_reference_psfex
            ),
            # Swarp(),
            Sextractor(config_path='winterdrp/pipelines/wirc_imsub/config/photomCat.sex',
                       parameter_path='winterdrp/pipelines/wirc_imsub/config/photom.param',
                       filter_path='winterdrp/pipelines/wirc_imsub/config/default.conv',
                       starnnw_path='winterdrp/pipelines/wirc_imsub/config/default.nnw',
                       output_sub_dir='subtract',
                       cache=False),
            PSFex(config_path='winterdrp/pipelines/wirc_imsub/config/photom.psfex',
                  output_sub_dir="subtract",
                  norm_fits=True),
            ZOGYPrepare(output_sub_dir="subtract"),
            ZOGY(output_sub_dir="subtract"),
            DetectCandidates(output_sub_dir="subtract",
                             cand_det_sextractor_config='winterdrp/pipelines/wirc_imsub/config/photomCat.sex',
                             cand_det_sextractor_nnw='winterdrp/pipelines/wirc_imsub/config/default.nnw',
                             cand_det_sextractor_filter='winterdrp/pipelines/wirc_imsub/config/default.conv',
                             cand_det_sextractor_params='winterdrp/pipelines/wirc_imsub/config/Scorr.param'),
            RegionsWriter(output_dir_name='candidates'),
            PSFPhotometry(),
            DataframeWriter(output_dir_name='candidates'),
            XMatch(
                catalog=TMASS(kowalski=get_kowalski()),
                num_stars=3,
                search_radius_arcsec=30
            ),
            XMatch(
                catalog=PS1(kowalski=get_kowalski()),
                num_stars=3,
                search_radius_arcsec=30
            ),
            DataframeWriter(output_dir_name='kowalski'),
            # EdgeCandidatesMask(edge_boundary_size=100)
            # FilterCandidates(),
            AvroPacketMaker(output_sub_dir="avro",
                            base_name="WNTR")
        ]
    }
