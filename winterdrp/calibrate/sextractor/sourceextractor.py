import os
import logging
import subprocess
import sys
from pathlib import Path
import docker
import shutil
from winterdrp.paths import calibration_config_dir
from docker.errors import DockerException
from winterdrp.utils.dockerutil import new_container, docker_path, docker_batch_put, docker_get_new_files

logger = logging.getLogger(__name__)

sextractor_cmd = os.getenv("SEXTRACTOR_CMD")


def local_sextractor(
        cmd: str,
        output_dir: str
):
    """
    Function to run sextractor on local machine using subprocess. It will only work if you have installed sextractor
    correctly, and specified the command to run sextractor with:
        export SEXTRACTOR_CMD = '/path/to/sextractor/executable/file

    After sextractor has been run using the specified 'cmd' command,
     all newly-generated files will be copied out of the current directory to 'output_dir'

    Parameters
    ----------
    cmd: A string containing the command you want to use to run sextractor. An example would be:
        cmd = '/usr/bin/source-extractor image0001.fits -c sex.config'
    output_dir: A local directory to save the output files to.

    Returns
    -------

    """

    try:

        # See what files are in the directory beforehand

        ignore_files = subprocess.run("ls", check=True, capture_output=True).stdout.decode().split("\n")

        # Run sextractor

        rval = subprocess.run(cmd.split(), check=True, capture_output=True)

        logger.debug(f'Sextractor ran successfully on image {cmd.split(" ")[1]}')
        logger.debug(rval.stdout.decode())

        try:
            os.makedirs(output_dir)
        except OSError:
            pass

        # Move new files to output dir

        new_files = [
            x for x in subprocess.run("ls", check=True, capture_output=True).stdout.decode().split("\n")
            if x not in ignore_files
        ]

        current_dir = subprocess.run("pwd", check=True, capture_output=True).stdout.decode().strip()

        for file in new_files:

            current_path = os.path.join(current_dir, file)
            output_path = os.path.join(output_dir, file)

            logger.debug(f"Moving {current_path} to {output_path}")

            shutil.move(current_path, output_path)

        return 0

    except (subprocess.CalledProcessError, FileNotFoundError) as err:
        logger.error(f'Could not run sextractor with error {err}')
        raise err


def temp_config(
        config_path: str,
        output_dir: str
) -> str:
    basename = f"temp_{os.path.basename(config_path)}"
    return os.path.join(output_dir, basename)


def docker_sextractor(
        cmd: str,
        output_dir: str,
):
    """Function to run sextractor via Docker. A container will be generated automatically,
    but a Docker server must be running first. You can start one via the Desktop application,
    or on the command line with `docker start'.

    After sextractor has been run using the specified 'cmd' command,
     all newly-generated files will be copy_list out of the container to 'output_dir'

    Parameters
    ----------
    cmd: A string containing the base arguments you want to use to run sextractor. An example would be:
        cmd = 'image01.fits -c sex.config'
    output_dir: A local directory to save the output files to.

    Returns
    -------

    """

    container = new_container()

    try:

        container.attach()

        container.start()

        split = cmd.split(" -")

        # Reorganise the commands so that each '-x' argument is grouped together
        # Basically still work even if someone puts the filename in a weird place

        sorted_split = []

        for i, arg in enumerate(split):
            sep = arg.split(" ")
            sorted_split.append(" ".join(sep[:2]))
            if len(sep) > 2:
                sorted_split[0] += " " + " ".join(sep[2:])

        new_split = []

        # Loop over sextractor command, and
        # copy everything that looks like a file into container

        copy_list = []

        config_file = None

        for i, arg in enumerate(sorted_split):
            sep = arg.split(" ")

            if sep[0] == "c":
                config_file = sep[1]

            new = list(sep)

            for j, x in enumerate(sep):
                if os.path.isfile(x):
                    new[j] = docker_path(sep[j])
                    copy_list.append(sep[j])

            new_split.append(" ".join(new))

        cmd = " -".join(new_split)

        # Be extra clever: go through config file and check there too!

        new_config_file = []

        if config_file is not None:
            with open(config_file, "rb") as f:
                for line in f.readlines():
                    args = [x for x in line.decode().split(" ") if x not in [""]]
                    new_args = list(args)
                    for i, arg in enumerate(args):
                        if os.path.isfile(arg):
                            copy_list.append(arg)
                            new_args[i] = docker_path(arg)
                    new_config_file.append(" ".join(new_args))

            temp_config_path = temp_config(config_file, output_dir)

            with open(temp_config_path, "w") as g:
                g.writelines(new_config_file)

            copy_list.append(temp_config_path)

            cmd = cmd.replace(docker_path(config_file), docker_path(temp_config_path))

        # Copy in files, and see what files are already there

        copy_list = list(set(copy_list))

        logger.debug(f"Copying {copy_list} into container")

        ignore_files = docker_batch_put(
            container=container,
            local_paths=copy_list
        )

        logger.debug(f"Ignoring files {ignore_files}")

        # Run sextractor

        log = container.exec_run(cmd, stderr=True, stdout=True)

        if not log.output == b"":
            logger.warning(f"Sextractor warning: {log.output.decode()}")

        if not log.exit_code == 0:
            err = f"Error running command: \n '{cmd}'\n which resulted in returncode '{log.exit_code}' and" \
                  f"the following error message: \n '{log.output.decode()}'"
            logger.error(err)
            raise subprocess.CalledProcessError(
                returncode=log.exit_code,
                cmd=cmd,
                stderr=log.output.decode()
            )

        # Copy out any files which did not exist before running sextractor

        docker_get_new_files(
            container=container,
            output_dir=output_dir,
            ignore_files=ignore_files
        )

    except docker.errors.APIError as err:
        logger.error(err)
        raise err
    finally:
        # In any case, clean up by killing the container and removing files

        container.kill()
        container.remove()


# Either run sextractor locally or on docker

if sextractor_cmd is None:
    sextractor_cmd = "/usr/bin/source-extractor"
    execute_sextractor = docker_sextractor
else:
    execute_sextractor = local_sextractor


# Functions to parse commands and generate appropriate sextractor files

def parse_checkimage(
    checkimage_type: str | list = None,
    image: str = None,
):
    """Function to parse the "checkimage" component of Sextractor configuration.

    Parameters
    ----------
    checkimage_type: The 'CHECKIMAGE_TYPE' files for sextractor. The default is None. To quote sextractor,
    available types are: 'NONE, BACKGROUND, BACKGROUND_RMS, MINIBACKGROUND, MINIBACK_RMS, -BACKGROUND,
    FILTERED, OBJECTS, -OBJECTS, SEGMENTATION, or APERTURES'. Multiple arguments should be specified in a list.
    image: The name of the image in question. If specified, the name of each checkimage will include the
    name of the original base image.

    Returns
    -------
    cmd: A string containing the partial sextractor command relating to checkimages. The default is an empty string.
    """
    if isinstance(checkimage_type, str):
        checkimage_type = list(checkimage_type)

    cmd = ""

    if image is not None:
        base_name = f'{os.path.basename(image).split(".")[0]}_'
    else:
        base_name = ""

    if checkimage_type is not None:
        cmd = "-CHECKIMAGE_TYPE " + ",".join(checkimage_type)
        cmd += " -CHECKIMAGE_NAME " + ",".join([
            f"{base_name}check_{x.lower()}.fits" for x in checkimage_type
        ])
        cmd += " "

    return cmd


default_config = os.path.join(calibration_config_dir, 'astrom.sex')


def run_sextractor(
        images: str | list,
        output_dir: str,
        config: str = default_config,
        param: str = os.path.join(calibration_config_dir, 'astrom.param'),
        filter_name: str = os.path.join(calibration_config_dir, 'default.conv'),
        star_nnw: str = os.path.join(calibration_config_dir, 'default.nnw'),
        weight_image: str = None,
        verbose_type: str = "QUIET",
        checkimage_type: str | list = None,
        reprocess: bool = True
):

    if not isinstance(images, list):
        images = [images]

    # Make output directory if it doesn't exist

    try:
        os.makedirs(output_dir)
    except OSError:
        pass

    for img in images:
        image_name = Path(img).stem
        output_catalog = f'{image_name}.cat'

        cmd = f"{sextractor_cmd} {img} " \
              f"-c {config} " \
              f"-CATALOG_NAME {output_catalog} " \
              f"-PARAMETERS_NAME {param} " \
              f"-FILTER_NAME {filter_name} " \
              f"-STARNNW_NAME {star_nnw} " \
              f"-VERBOSE_TYPE {verbose_type} "

        cmd += parse_checkimage(
            checkimage_type=checkimage_type,
            image=img
        )

        if weight_image is None:
            cmd += "-WEIGHT_TYPE None"
        else:
            cmd += f"-WEIGHT_IMAGE {weight_image}"

        if not reprocess:

            output_cat_path = os.path.join(output_dir, output_catalog)

            if os.path.exists(output_cat_path):
                logger.debug(f"Skipping because {output_cat_path} already exist.")
                continue

        logger.debug(f"Using '{['local', 'docker'][sextractor_cmd == local_sextractor]}' "
                     f"sextractor installation to run `{cmd}`")

        execute_sextractor(cmd, output_dir)


if __name__ == "__main__":
    run_sextractor(
        "/Users/robertstein/Data/WIRC/20200929/redux/image0240.fits",
        "/Users/robertstein/Data/testersextractor",
        checkimage_type=["BACKGROUND", "BACKGROUND_RMS"]
    )