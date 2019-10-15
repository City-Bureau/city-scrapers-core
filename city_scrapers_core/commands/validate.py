import os
from importlib import import_module

from scrapy.commands import ScrapyCommand

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
        spider_list = self.crawler_process.spider_loader.list()
        spiders = [spider for spider in args if spider in spider_list]
        if len(spiders) == 0 and not opts.all:
            print("No spiders provided, exiting...")
            return
        elif opts.all:
            spiders = spider_list
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

    @property
    def spiders_dir(self):
        spiders_module = import_module(self.settings.get("NEWSPIDER_MODULE"))
        return os.path.relpath(os.path.dirname(spiders_module.__file__))
