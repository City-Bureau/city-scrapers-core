from setuptools import find_packages, setup

with open("README.md", "r") as f:
    long_description = f.read()


setup(
    name="city-scrapers-core",
    version="0.1.4",
    license="MIT",
    author="Pat Sier",
    author_email="pat@citybureau.org",
    description="Core functionality for City Scrapers projects",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/City-Bureau/city-scrapers-core",
    packages=find_packages(),
    package_data={"": ["*"], "city_scrapers_core": ["templates/*"]},
    install_requires=["jsonschema>=3.0.0a5", "legistar", "pytz", "requests", "scrapy"],
    tests_requires=["flake8", "pytest", "isort"],
    extras_requires={"aws": ["boto3"], "azure": ["azure-storage-blob"]},
    dependency_links=[
        "https://github.com/opencivicdata/python-legistar-scraper/zipball/bf25cc94980f1608b4cc6766529f1155a273e049#egg=legistar"  # noqa
    ],
    python_requires=">=3.5,<4.0",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Framework :: Scrapy",
    ],
)
