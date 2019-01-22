from scrapy.commands import ScrapyCommand


class Command(ScrapyCommand):
    requires_project = True

    def syntax(self):
        return "[options"

    def short_desc(self):
        return "Run all spiders in a project"

    def run(self, args, opts):
        for spider in self.crawler_process.spider_loader.list():
            self.crawler_process.crawl(spider)
        self.crawler_process.start()
