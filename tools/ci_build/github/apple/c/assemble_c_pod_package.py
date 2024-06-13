#!/usr/bin/env python3

# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import argparse
import pathlib
import shutil
import sys

_script_dir = pathlib.Path(__file__).parent.resolve(strict=True)
sys.path.append(str(_script_dir.parent))


from package_assembly_utils import (  # noqa: E402
    PackageVariant,
    copy_repo_relative_to_dir,
    gen_file_from_template,
    load_json_config,
)


def get_pod_config_file(package_variant: PackageVariant):
    """
    Gets the pod configuration file path for the given package variant.
    """
    if package_variant == PackageVariant.Full:
        return _script_dir / "onnxruntime-c.config.json"
    elif package_variant == PackageVariant.Training:
        return _script_dir / "onnxruntime-training-c.config.json"
    else:
        raise ValueError(f"Unhandled package variant: {package_variant}")


def assemble_c_pod_package(
    staging_dir: pathlib.Path,
    pod_version: str,
    framework_info_file: pathlib.Path,
    public_headers_dir: pathlib.Path,
    framework_dir: pathlib.Path,
    package_variant: PackageVariant,
):
    """
    Assembles the files for the C/C++ pod package in a staging directory.

    :param staging_dir Path to the staging directory for the C/C++ pod files.
    :param pod_version C/C++ pod version.
    :param framework_info_file Path to the framework_info.json or xcframework_info.json file containing additional values for the podspec.
    :param public_headers_dir Path to the public headers directory to include in the pod.
    :param framework_dir Path to the onnxruntime framework directory to include in the pod.
    :param package_variant The pod package variant.
    :return Tuple of (package name, path to the podspec file).
    """
    staging_dir = staging_dir.resolve()
    framework_info_file = framework_info_file.resolve(strict=True)
    public_headers_dir = public_headers_dir.resolve(strict=True)
    framework_dir = framework_dir.resolve(strict=True)

    framework_info = load_json_config(framework_info_file)
    pod_config = load_json_config(get_pod_config_file(package_variant))

    pod_name = pod_config["name"]

    print(f"Assembling files in staging directory: {staging_dir}")
    if staging_dir.exists():
        print("Warning: staging directory already exists", file=sys.stderr)

    # copy the necessary files to the staging directory
    shutil.copytree(framework_dir, staging_dir / framework_dir.name, dirs_exist_ok=True)
    shutil.copytree(public_headers_dir, staging_dir / public_headers_dir.name, dirs_exist_ok=True)
    copy_repo_relative_to_dir(["LICENSE"], staging_dir)

    # generate the podspec file from the template
    variable_substitutions = {
        "DESCRIPTION": pod_config["description"],
        # By default, we build both "iphoneos" and "iphonesimulator" architectures, and the deployment target should be the same between these two.
        "IOS_DEPLOYMENT_TARGET": framework_info["iphonesimulator"]["APPLE_DEPLOYMENT_TARGET"],
        "MACOSX_DEPLOYMENT_TARGET": framework_info.get("macosx", {}).get("APPLE_DEPLOYMENT_TARGET", ""),
        "LICENSE_FILE": "LICENSE",
        "NAME": pod_name,
        "ORT_C_FRAMEWORK": framework_dir.name,
        "ORT_C_HEADERS_DIR": public_headers_dir.name,
        "SUMMARY": pod_config["summary"],
        "VERSION": pod_version,
        "WEAK_FRAMEWORK": framework_info["iphonesimulator"]["WEAK_FRAMEWORK"],
    }

    podspec_template = _script_dir / "c.podspec.template"
    podspec = staging_dir / f"{pod_name}.podspec"

    gen_file_from_template(podspec_template, podspec, variable_substitutions)

    return pod_name, podspec


def parse_args():
    parser = argparse.ArgumentParser(
        description="""
        Assembles the files for the C/C++ pod package in a staging directory.
        This directory can be validated (e.g., with `pod lib lint`) and then zipped to create a package for release.
    """
    )

    parser.add_argument(
        "--staging-dir",
        type=pathlib.Path,
        default=pathlib.Path("./c-staging"),
        help="Path to the staging directory for the C/C++ pod files.",
    )
    parser.add_argument("--pod-version", required=True, help="C/C++ pod version.")
    parser.add_argument(
        "--framework-info-file",
        type=pathlib.Path,
        required=True,
        help="Path to the framework_info.json or xcframework_info.json file containing additional values for the podspec. "
        "This file should be generated by CMake in the build directory.",
    )
    parser.add_argument(
        "--public-headers-dir",
        type=pathlib.Path,
        required=True,
        help="Path to the public headers directory to include in the pod.",
    )
    parser.add_argument(
        "--framework-dir",
        type=pathlib.Path,
        required=True,
        help="Path to the onnxruntime framework directory to include in the pod.",
    )
    parser.add_argument(
        "--variant", choices=PackageVariant.all_variant_names(), required=True, help="Pod package variant."
    )

    return parser.parse_args()


def main():
    args = parse_args()

    assemble_c_pod_package(
        staging_dir=args.staging_dir,
        pod_version=args.pod_version,
        framework_info_file=args.framework_info_file,
        public_headers_dir=args.public_headers_dir,
        framework_dir=args.framework_dir,
        package_variant=PackageVariant[args.variant],
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
