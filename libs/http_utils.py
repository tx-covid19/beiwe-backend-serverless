from pprint import pprint


def checkbox_to_boolean(list_checkbox_params, dict_all_params):
    """ Takes a list of strings that are to be processed as checkboxes on a post
        parameter, (checkboxes supply some arbitrary value in a post if they are
        checked, and no value at all if they are not checked.), and a dict of
        parameters and their values to update.
        returns a dictionary with modified/added values containing appropriate
        booleans."""
    for param in list_checkbox_params:
        if param not in dict_all_params:
            dict_all_params[param] = False
        else:
            dict_all_params[param] = True
    return dict_all_params


def combined_multi_dict_to_dict(cmd):
    return { key: value for key, value in cmd.items() }