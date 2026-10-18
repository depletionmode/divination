from pathlib import Path

from setuptools import find_packages, setup


setup(
    name="divination",
    version="2.1.0",
    author="David Kaplan <@depletionmode>",
    description="Python module for hardware and physmem inspection",
    long_description=Path(__file__).with_name("README.rst").read_text(encoding="utf-8"),
    long_description_content_type="text/x-rst",
    url="https://github.com/depletionmode/divination",
    packages=find_packages(include=["divination", "divination.*"]),
    python_requires=">=3.9",
    install_requires=['pywin32; sys_platform == "win32"'],
    extras_require={"examples": ["tqdm"]},
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX :: Linux",
        "License :: OSI Approved :: MIT License",
        "Development Status :: 4 - Beta",
    ],
    include_package_data=True,
)
