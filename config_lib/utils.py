import os
import pathlib
import re
from datetime import datetime
from functools import lru_cache
from tkinter import Tk
from tkinter.filedialog import askopenfilename, askdirectory

from matplotlib import pyplot as plt


def cached_caller(callable, hashable_transform=str, *args, **kwargs):
    """
    A function to wrap the arguments of a callable into hashable containers, then run the callable with lru_cache turned on.
    The hashable transform is a callable used to transform the args and kwargs into a form that implements the __hash__()
    and __eq__() methods.

    TODO: Add ability to control the size of the lru_cache
    TODO: Add ability to specify a different hashable transform for each arg and kwarg

    Parameters
    ----------
    callable: callable to call with lru_cache
    hashable_transform: callable. default is str. Another option is pickle.dumps. If None is passed, the arguments must
                        already be hashable
    args: args for callable
    kwargs: kwargs for callable

    Returns
    -------
    result of callable

    """
    if hashable_transform is not None:
        hashable_args = [HashableContainer(arg, hashable_transform) for arg in args]
        hashable_kwargs = {key: HashableContainer(val, hashable_transform) for key, val in kwargs.items()}
    else:
        hashable_args = args
        hashable_kwargs = kwargs
    return _call_with_hashables(callable, *hashable_args, **hashable_kwargs)


class HashableContainer:
    def __init__(self, object, hashable_transform):
        self.object = object
        self.hash_trans = hashable_transform

    def __eq__(self, other):
        return self.hash_trans(self.object) == self.hash_trans(other.object)

    def __hash__(self):
        return hash(self.hash_trans(self.object))


@lru_cache(maxsize=100)
def _call_with_hashables(wrapped, *hashable_args, **hashable_kwargs):
    original_args = [arg.object for arg in hashable_args]
    original_kwargs = {key: val.object for key, val in hashable_kwargs.items()}
    result = wrapped(*original_args, **original_kwargs)
    return result


def get_input(data, show_columns, test_name):
    ax = data[show_columns].plot()
    ax.text(1.025, 0.985, "Add point: Mouse left\nRemove point: Mouse right\nClose: Mouse middle",
            transform=ax.transAxes, va="top", bbox=dict(ec=(0, 0, 0), fc=(1, 1, 1)))
    ax.set_title("Input for " + test_name)
    ax.figure.tight_layout(pad=1)
    points = plt.ginput(n=-1, timeout=0)
    return points


def get_filename(config=None, key="data", remember_directory=True):
    # Todo: we probably should put the config stuff in a separate function.
    return _get_filename_or_directory(config=config, key=key, which="filename", remember_directory=remember_directory)


def get_directory(config=None, key="data", remember_directory=True):
    return _get_filename_or_directory(config=config, key=key, which="directory", remember_directory=remember_directory)


def _get_filename_or_directory(config=None, key="data", which="filename", remember_directory=True):
    """
    Finds a filename by asking the user through a Tk file select dialog.
    If remember_directory is set to True, the directory is remembered for next time
    If the filename key exists in the input config, this is used instead of the dialog

    Parameters
    ----------
    config
    key
    which
    remember_directory

    Returns
    -------
    item
        config or directory name

    """
    if config is not None and key in config:
        item = config[key]  # Secret option to not get dialog
    else:
        Tk().withdraw()  # we don't want a full GUI, so keep the root window from appearing
        try:
            initial_dir = None
            if config is not None and f"initial_{key}_directory" in config:
                initial_dir = config[f"initial_{key}_directory"]

            if which == "filename":
                item = askopenfilename(initialdir=initial_dir, title=f"Select {key} file")
            else:
                item = askdirectory(initialdir=initial_dir, title=f"Select {key} directory")

        except FileNotFoundError:
            raise

        if item == "" or item == ():
            error_message = f"Invalid {which} selection"
            raise ValueError(error_message)

        if config is not None and remember_directory:
            if which == "directory":
                directory = item
            else:
                directory = str(pathlib.Path(item).parent)

            if f"initial_{key}_directory" not in config or directory != config[f"initial_{key}_directory"]:
                config[f"initial_{key}_directory"] = directory
                config.save()

        return item


def parse_relative_paths(input_dict, alternate_working_directory, awd_indicator="alternate", path_tag="filename",
                         wd_tag="_wd"):
    """
    Modify paths in an input dict to make them relative to an alternate working directory if indicated.

    Parameters
    ----------
    input_dict
    alternate_working_directory
    awd_indicator
    path_tag
    wd_tag

    Returns
    -------

    """
    for key, value in input_dict.items():
        # check if key indicates that this is a path
        if re.match(".*(?:" + path_tag + "$)", key) is not None:
            # check if the dict contains an instruction to modify the identified path
            if key + wd_tag in input_dict:
                # if the instruction is awd_indicator, we prepend the alternate working directory to the path
                if input_dict[key + wd_tag] == awd_indicator:
                    input_dict[key] = alternate_working_directory + "/" + input_dict[key]
                # else we just assume prepend whatever we see
                else:
                    input_dict[key] = input_dict[key + wd_tag] + "/" + input_dict[key]


def create_unique_timestamped_file_name(directory=".", date_format="%Y-%m-%dT%H_%M", prefix="", suffix="", extension=""):
    # TODO: don't create the directory (for better separation of concerns)
    if not os.path.exists(directory):
        os.mkdir(directory)

    if prefix != "":
        prefix = prefix + "_"
    if suffix != "":
        suffix = "_" + suffix

    file_name = prefix + datetime.now().strftime(date_format) + suffix

    addition = ""
    i = 0
    while True:
        try_name = directory + "/" + file_name + addition + extension
        if not(os.path.exists(try_name)):
            return try_name
        i += 1
        addition = "_" + str(i)