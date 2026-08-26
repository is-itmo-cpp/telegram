from itmogus.core.config import config


ALLOWED_LAB_NAMES = {"livecoding2"}


def resolve_lab_name(user_input: str) -> str | None:
    name = user_input.strip().lower()

    if name.isdigit():
        number = int(name)
        if number < 1:
            return None
        return f"labwork{number}"

    if name.startswith("labwork") and name.removeprefix("labwork").isdigit():
        number = int(name.removeprefix("labwork"))
        if number < 1:
            return None
        return f"labwork{number}"

    if name in ALLOWED_LAB_NAMES:
        return name

    return None


def get_template_repo_name(lab_name: str) -> str:
    return f"{config.github_classroom}-{lab_name}-{lab_name}"


def get_student_repo_name(lab_name: str, github_username: str) -> str:
    return f"{lab_name}-{github_username}"
