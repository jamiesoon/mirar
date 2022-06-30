import astropy.io.fits
import numpy as np
import logging
from winterdrp.processors.base_processor import BaseProcessor

logger = logging.getLogger(__name__)


def select_from_images(
        images: list[np.ndarray],
        headers: list[astropy.io.fits.Header],
        header_key: str = "target",
        target_values: str | list[str] = "science",
) -> tuple[list[np.ndarray], list[astropy.io.fits.Header]]:

    if isinstance(target_values, str):
        target_values = [target_values]

    passing_images = []
    passing_headers = []

    for i, header in enumerate(headers):
        if header[header_key] in target_values:
            passing_images.append(images[i])
            passing_headers.append(header)

    return passing_images, passing_headers


class ImageSelector(BaseProcessor):

    base_key = "select"

    def __init__(
            self,
            # header_keys: str | list[str] = "target",
            # header_values: list[list[str] | str] = "science",
            *args: tuple[str, str | list[str]],
            **kwargs
    ):
        super().__init__(*args, **kwargs)

        # if isinstance(header_keys, str):
        #     header_keys = [header_keys]
        #
        # if isinstance(header_keys, str):
        #     header_keys = [header_keys]

        self.targets = args

        # self.header_keys = header_keys
        # self.target_values = header_values
        #
        # if len(self.header_keys) != len(self.target_values):
        #     err = f"Mismatch in length. Each key should have a corresponding value/list of values.:\n " \
        #           f"{self.header_keys}, {self.target_values}"
        #     logger.error(err)
        #     raise ValueError(err)

    def _apply_to_images(
            self,
            images: list[np.ndarray],
            headers: list[astropy.io.fits.Header],
    ) -> tuple[list[np.ndarray], list[astropy.io.fits.Header]]:

        for (header_key, target_values) in self.targets:

            print(header_key, target_values)

            images, headers = select_from_images(
                images,
                headers,
                header_key=header_key,
                target_values=target_values
            )
            print(len(images))

        return images, headers


def split_images_into_batches(
        images: list[np.ndarray],
        headers: list[astropy.io.fits.Header],
        split_key: str | list[str]
) -> list[list[list[np.ndarray], list[astropy.io.fits.Header]]]:

    if isinstance(split_key, str):
        split_key = [split_key]

    groups = dict()

    for i, header in enumerate(headers):
        uid = []

        for key in split_key:
            uid.append(str(header[key]))

        uid = "_".join(uid)

        if uid not in groups.keys():
            groups[uid] = [[images[i]], [header]]
        else:
            groups[uid][0] += [images[i]]
            groups[uid][1] += [header]

    return [x for x in groups.values()]


class ImageBatcher(BaseProcessor):

    base_key = "batch"

    def __init__(
            self,
            split_key: str | list[str],
            *args,
            **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.split_key = split_key

    def _apply_to_images(
            self,
            images: list[np.ndarray],
            headers: list[astropy.io.fits.Header],
    ) -> tuple[list[np.ndarray], list[astropy.io.fits.Header]]:
        return images, headers

    def update_batches(
        self,
        batches: list[list[list[np.ndarray], list[astropy.io.fits.header]]]
    ) -> list[list[list[np.ndarray], list[astropy.io.fits.header]]]:

        new_batches = []

        for [images, headers] in batches:
            new_batches += split_images_into_batches(images, headers, split_key=self.split_key)

        return new_batches

