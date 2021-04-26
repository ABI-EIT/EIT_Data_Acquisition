

data_directory = ""
subject_directory_glob = "Subject *"
tests = ["drift", "linearity"]
meshes = {
    "generic_chest": "mesh/",
    "oval": "mesh/",
    "generic_lungs": "mesh/"
}

configurations = [
    {
        "mesh": "generic_chest",
        "electrode_placement": "equal_spaced_single_gap_chest_and_spine"
    },
    {
        "mesh": "oval",
    },
    {
        "mesh": "generic_chest",
        "electrode_placement": "subject_lidar"
    },
    {
        "mesh": "subject_lidar"
    },
    {
        "mesh": "subject_pca"
    },
    {
        "mesh": "generic_chest",
        "mask": "generic_lungs"
    }

]


# Open all subject data files and check for ginput
# for each configuration, for each subject, for each test. Run code. TDQM on these three levels
