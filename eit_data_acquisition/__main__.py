import argparse
import shutil

import PyInstaller.__main__
import os
import eit_data_acquisition

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", help="Install the app",  action="store_true")
    args = parser.parse_args()

    if args.install is not False:
        install()
    else:
        print("No action specified")


def install():
    package_dir = os.path.dirname(eit_data_acquisition.__file__)
    working_dir = os.getcwd()
    workpath = os.path.join(working_dir, "build")
    distpath = os.path.join(working_dir, "eit_app")
    specpath = working_dir

    app_path = os.path.join(package_dir, "main.py")
    layout_path = os.path.join(package_dir, "layout", "layout.ui")
    lung_icon_path = os.path.join(package_dir, "layout", "lung_icon.PNG")
    conf_path = os.path.join(package_dir, "configuration", "conf.json")
    eit_setup_path = os.path.join(package_dir, "configuration", "eit_setup.json")
    mesh_path = os.path.join(package_dir, "configuration", "circle_phantom_mesh_no_inclusion.stl")

    if os.path.exists(distpath):
        shutil.rmtree(distpath)

    sep = os.pathsep
    PyInstaller.__main__.run([
        app_path,
        "--add-data=" + layout_path + sep + "layout",
        "--add-data=" + lung_icon_path + sep + "layout",
        "--add-data=" + conf_path + sep + "configuration",
        "--add-data=" + eit_setup_path + sep + "configuration",
        "--add-data=" + mesh_path + sep + "configuration",
        "--windowed",
        "--workpath=" + workpath,
        "--distpath=" + distpath,
        "--onedir"
    ])

    # Get rid of pyinstaller working files
    shutil.rmtree(workpath)
    os.remove(os.path.join(specpath, "main.spec"))
    

if __name__ == "__main__":
    main()
