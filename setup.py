from pathlib import Path

from setuptools import find_packages, setup


setup(
    name="divination",
    version="2.2.0",
    author="David Kaplan <@depletionmode>",
    description="Python hardware inspection: PCI configuration, MSRs, MMIO, and Linux physical memory",
    long_description=Path(__file__).with_name("README.rst").read_text(encoding="utf-8"),
    long_description_content_type="text/x-rst",
    url="https://github.com/depletionmode/divination",
    project_urls={
        "Documentation": "https://github.com/depletionmode/divination/blob/master/docs/usage.rst",
        "Source": "https://github.com/depletionmode/divination",
        "Issues": "https://github.com/depletionmode/divination/issues",
    },
    keywords="hardware-inspection,pci,msr,mmio,physical-memory,linux,windows,x86-64",
    packages=find_packages(include=["divination", "divination.*"]),
    python_requires=">=3.9",
    install_requires=['pywin32; sys_platform == "win32"'],
    extras_require={"examples": ["tqdm"]},
    entry_points={"console_scripts": ["divination=divination.cli:main"]},
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX :: Linux",
        "Topic :: System :: Hardware",
        "License :: OSI Approved :: MIT License",
        "Development Status :: 4 - Beta",
    ],
    include_package_data=True,
)
