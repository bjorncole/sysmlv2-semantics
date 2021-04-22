# A set of tools to make interpretations easier to read
from ..widget.labeling import get_m1_signature_label


def pprint_interpretation(interpretation: dict, all_elements: dict) -> str:
    print_lines = []
    for key, val in interpretation.items():
        print_lines.append(get_m1_signature_label(all_elements[key], all_elements) + ', id = ' + key + ', size = ' + str(len(val)))
        short_list = []
        for indx, ind_val in enumerate(val):
            if indx < 5:
                short_list.append(ind_val)
        if len(val) > 4:
            short_list.append(['..'])

        print_lines.extend(short_list)
    return print_lines