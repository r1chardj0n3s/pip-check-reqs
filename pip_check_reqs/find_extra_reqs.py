import collections
import importlib.metadata
import logging
import pathlib
import optparse
import os
import sys

from packaging.utils import canonicalize_name
from pip._internal.commands.show import search_packages_info
from pip_check_reqs import common
from pip_check_reqs.common import version_info

log = logging.getLogger(__name__)


def find_extra_reqs(options, requirements_filename):
    # 1. find files used by imports in the code (as best we can without
    #    executing)
    used_modules = common.find_imported_modules(options)

    # 2. find which packages provide which files
    installed_files = {}
    all_pkgs = (
        dist.metadata["Name"] for dist
        in importlib.metadata.distributions()
    )

    for package in search_packages_info(all_pkgs):
        if isinstance(package, dict):  # pragma: no cover
            package_name = package['name']
            package_location = package['location']
            package_files = package.get('files', []) or []
        else:  # pragma: no cover
            package_name = package.name
            package_location = package.location
            package_files = []
            for item in (package.files or []):
                item_location_rel = (pathlib.Path(package_location) / item)
                item_location = item_location_rel.resolve()
                try:
                    relative_item_location = item_location.relative_to(package_location)
                except ValueError:
                    # Ideally we would use Pathlib.is_relative_to rather than
                    # checking for a ValueError, but that is only available in
                    # Python 3.9+.
                    relative_item_location = item_location
                package_files.append(str(relative_item_location))

        log.debug('installed package: %s (at %s)', package_name,
                  package_location)
        for package_file in package_files:
            path = os.path.realpath(
                os.path.join(package_location, package_file),
            )
            installed_files[path] = package_name
            package_path = common.is_package_file(path)
            if package_path:
                # we've seen a package file so add the bare package directory
                # to the installed list as well as we might want to look up
                # a package by its directory path later
                installed_files[package_path] = package_name

    # 3. match imported modules against those packages
    used = collections.defaultdict(list)

    for modname, info in used_modules.items():
        # probably standard library if it's not in the files list
        if info.filename in installed_files:
            used_name = canonicalize_name(installed_files[info.filename])
            log.debug('used module: %s (from package %s)', modname,
                      installed_files[info.filename])
            used[used_name].append(info)
        else:
            log.debug(
                'used module: %s (from file %s, assuming stdlib or local)',
                modname, info.filename)

    # 4. compare with requirements
    explicit = common.find_required_modules(
        options=options,
        requirements_filename=requirements_filename,
    )

    return [name for name in explicit if name not in used]


def main():
    usage = 'usage: %prog [options] files or directories'
    parser = optparse.OptionParser(usage)
    parser.add_option("--requirements-file",
                      dest="requirements_filename",
                      metavar="PATH",
                      default="requirements.txt",
                      help="path to the requirements file "
                           "(defaults to \"requirements.txt\")")
    parser.add_option("-f",
                      "--ignore-file",
                      dest="ignore_files",
                      action="append",
                      default=[],
                      help="file paths globs to ignore")
    parser.add_option("-m",
                      "--ignore-module",
                      dest="ignore_mods",
                      action="append",
                      default=[],
                      help="used module names (globs are ok) to ignore")
    parser.add_option("-r",
                      "--ignore-requirement",
                      dest="ignore_reqs",
                      action="append",
                      default=[],
                      help="reqs in requirements to ignore")
    parser.add_option("-s",
                      "--skip-incompatible",
                      dest="skip_incompatible",
                      action="store_true",
                      default=False,
                      help="skip requirements that have incompatible "
                           "environment markers")
    parser.add_option("-v",
                      "--verbose",
                      dest="verbose",
                      action="store_true",
                      default=False,
                      help="be more verbose")
    parser.add_option("-d",
                      "--debug",
                      dest="debug",
                      action="store_true",
                      default=False,
                      help="be *really* verbose")
    parser.add_option("-V", "--version",
                      dest="version",
                      action="store_true",
                      default=False,
                      help="display version information")

    (options, args) = parser.parse_args()

    if options.version:
        print(version_info())
        sys.exit(0)

    if not args:
        parser.error("no source files or directories specified")
        sys.exit(2)

    options.ignore_files = common.ignorer(options.ignore_files)
    options.ignore_mods = common.ignorer(options.ignore_mods)
    options.ignore_reqs = common.ignorer(options.ignore_reqs)

    options.paths = args

    logging.basicConfig(format='%(message)s')
    if options.debug:
        level = logging.DEBUG
    elif options.verbose:
        level = logging.INFO
    else:
        level = logging.WARN
    log.setLevel(level)
    common.log.setLevel(level)

    log.info(version_info())

    extras = find_extra_reqs(
        options=options,
        requirements_filename=options.requirements_filename,
    )

    if extras:
        log.warning('Extra requirements:')
    for name in extras:
        message = '{name} in {requirements_filename}'.format(
            name=name,
            requirements_filename=options.requirements_filename,
        )
        log.warning(message)

    if extras:
        sys.exit(1)


if __name__ == '__main__':  # pragma: no cover
    main()
