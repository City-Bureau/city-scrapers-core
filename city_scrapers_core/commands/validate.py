import os
import re
import subprocess
from importlib import import_module

from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError

from ..pipelines import ValidationPipeline


class Command(ScrapyCommand):
    requires_project = True

    def syntax(self):
        return "[options] <spider>"

    def short_desc(self):
        return "Run a spider with validations, or validate all changed spiders in a PR"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option(
            "--all",
            dest="all",
            action="store_true",
            help="Run validation on all scrapers",
        )

    def run(self, args, opts):
        self._add_validation_pipeline()
        in_ci = os.getenv("CI")
        if len(args) < 1 and not in_ci and not opts.all:
            raise UsageError(
                "At least one spider must be supplied or --all flag must be supplied "
                "if not in CI environment"
            )
        if len(args) == 1:
            spiders = [args[0]]
        elif opts.all:
            spiders = self.crawler_process.spider_loader.list()
        elif in_ci:
            spiders = self._get_changed_spiders()
        if len(spiders) == 0:
            print("No spiders provided, exiting...")
            return
        for spider in spiders:
            self.crawler_process.crawl(spider)
        self.crawler_process.start()

    def _add_validation_pipeline(self):
        """Add validation pipeline to pipelines if not already present"""
        pipelines = self.settings.get("ITEM_PIPELINES", {})
        pipeline_name = ValidationPipeline.__name__
        # Exit if pipeline already included
        if any(pipeline_name in pipeline for pipeline in pipelines.keys()):
            return
        fullname = "{}.{}".format(ValidationPipeline.__module__, pipeline_name)
        priority = 1
        if len(pipelines.keys()) > 0:
            priority = max(pipelines.values()) + 1
        self.settings.set("ITEM_PIPELINES", {**pipelines, **{fullname: priority}})
        self.settings.set("CITY_SCRAPERS_ENFORCE_VALIDATION", True)

    def _get_changed_spiders(self):
        """Checks git diff for spiders that have changed"""
        changed_spiders = []
        travis_pr = os.getenv("TRAVIS_PULL_REQUEST")
        if not travis_pr or travis_pr == "false":
            print("Travis CI build not triggered by a pull request")
            return changed_spiders
        diff_output = subprocess.check_output(
            [
                "git",
                "diff",
                "--name-only",
                "--diff-filter=AM",
                os.getenv("TRAVIS_COMMIT_RANGE"),
            ]
        ).decode("utf-8")
        for filename in diff_output.split("\n"):
            spider = re.search(  # noqa
                "(?<={}/)\w+(?=\.py)".format(self.spiders_dir), filename
            )
            if spider:
                changed_spiders.append(spider.group())
        return changed_spiders

    @property
    def spiders_dir(self):
        spiders_module = import_module(self.settings.get("NEWSPIDER_MODULE"))
        return os.path.relpath(os.path.dirname(spiders_module.__file__))
