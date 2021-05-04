from deepmerge import always_merger
from pprint import pprint
import copy

big_dict = {
    "sub_dict": {
        "item_1": 2,
        "item_2": 3,
        "level_2_dict": {
            "item_1": 4,
            "item_2": 5,
        }
    },
    "list": [
        "item_1",
        "item_2",
        {"key_1": "dict_in_a_list"}
    ]
}

# # Updating and adding leaves is easy.
# # Actually for a list there's no way to know if you want to add or update. so default to add?
# # Or we might want to check if an item is there and add it if not
#
# # What if we want to replace a branch?
#
# # So 4 commands: update (leaf), add, replace (branch), remove
# # what if we want to update and add? try update and then try add?
#
# # or should we just make it impossible to update a list in order to avoid confusion?
#
# # How to indicate update a leaf in a list?
#
# # for combined function maybe have a list_action parameter to choose between add and replace (and update)?
#
to_update_leaves = {
    "sub_dict": {
        "item_2": "updated_item_2",
        "level_2_dict": {
            "item_3": "added_item_3"
        },
        "item_4": "Should error"
    },
    "list": [
        # *[None] * 2,
        {"key_a": "updated_leaf_in_list"}
    ]
}
#
# to_add = {
#     "sub_dict": {
#         "item_4": "New item"
#     },
#     "list": [
#         {"key_a": "added leaf in list"}
#     ]
# }
#
# to_replace_branches = {
#
# }
#
# to_remove_leaves = {
#     "sub_dict": {
#         "level_2_dict": {
#             "item_2": 5,
#         }
#     },
# }
#
# to_remove_branches = {
#     "sub_dict": {
#         "level_2_dict"
#     },
#     "list": [
#         {"key_a"}
#     ]
# }
#
# to_add_update = {
#     "sub_dict": {
#         "item_2": "updated_item_2",
#         "level_2_dict": {
#             "item_3": "added_item_3"
#         },
#         "item_4": "No longer error"
#     }
# }
#
#
# def recur_func(iterable, target):
#     for item in iterable:
#         if isinstance(item, Iterable):
#             # Recurse
#             pass
#         else:
#             # Do thing
#             pass

to_merge = copy.deepcopy(big_dict)
always_merger.merge(to_merge, to_update_leaves)

print("Original")
pprint(big_dict)

print("Update")
pprint(to_update_leaves)

print("Merged")
pprint(to_merge)