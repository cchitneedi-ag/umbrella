import re
from dataclasses import dataclass


@dataclass
class Component:
    """
    Virtual representation of components defined in the user_schema yaml.
    Definition: https://github.com/codecov/shared/pull/312/commits/c7bd48173da914bb16137526015791cb5a3c931c
    """

    component_id: str
    name: str
    flag_regexes: list[str]
    paths: list[str]
    statuses: list[dict]

    @classmethod
    def from_dict(cls, component_dict):
        return Component(
            component_id=component_dict.get("component_id", ""),
            name=component_dict.get("name", ""),
            flag_regexes=component_dict.get("flag_regexes", []),
            paths=component_dict.get("paths", []),
            statuses=component_dict.get("statuses", []),
        )

    def get_display_name(self) -> str:
        return self.name or self.component_id or "default_component"

    def get_matching_flags(self, current_flags: list[str]) -> list[str]:
        ans = set()
        compiled_regexes = (re.compile(flag_regex) for flag_regex in self.flag_regexes)
        for regex_to_match in compiled_regexes:
            matches_to_this_regex = filter(
                lambda flag: regex_to_match.match(flag), current_flags
            )
            ans.update(matches_to_this_regex)
        return list(ans)
