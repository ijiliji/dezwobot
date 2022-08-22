from setuptools import setup, find_packages


def _get_requirements(file_name: str = "requirements.txt") -> list:
      with open(file_name, "r") as in_file:
            return [line.strip() for line in in_file]

setup(
    name = "dezwobot",
    version = "0.0.1",
    author = "ijiliji",
    description = ("Bot for https://reddit.com/r/dezwo"),
    license = "MIT",
    url = "https://github.com/ijiliji/dezwobot",
    packages=find_packages(),
    install_requires=_get_requirements("requirements.txt")
)