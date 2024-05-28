def convert_snake_to_camel_case(string):
    camel_string = "".join(x.capitalize() for x in string.lower().split("_"))

    return camel_string


def convert_snake_to_lower_camel_case(string):
    camel_string = convert_snake_to_camel_case(string)
    lower_camel_string = camel_string[0].lower() + camel_string[1:]

    return lower_camel_string
