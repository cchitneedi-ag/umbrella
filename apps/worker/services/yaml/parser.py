from yaml import safe_load
from yaml.error import YAMLError

from shared.validation.exceptions import InvalidYamlException
from shared.yaml.validation import validate_yaml


def parse_yaml_file(content: str, show_secrets_for) -> dict | None:
    try:
        yaml_dict = safe_load(content)
    except YAMLError as e:
        raise InvalidYamlException("invalid_yaml", e)
    if yaml_dict is None:
        return None
    return validate_yaml(yaml_dict, show_secrets_for=show_secrets_for)
