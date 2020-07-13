import json
import logging
import shutil
import string
from datetime import datetime
from importlib import import_module
from os.path import abspath, dirname, join
from urllib.parse import urlparse

import requests
from legistar.events import LegistarEventsScraper
from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError
from scrapy.utils.template import render_templatefile

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.101 Safari/537.36"  # noqa

logger = logging.getLogger(__name__)


class Command(ScrapyCommand):
    requires_project = False
    default_settings = {"LOG_ENABLED": False}

    def syntax(self):
        return "<name> <agency> <start_url>"

    def short_desc(self):
        return "Generate a new spider and test file for a City Scrapers project"

    def run(self, args, opts):
        if len(args) != 3:
            raise UsageError()
        name, agency, start_url = args[0:3]
        domain = urlparse(start_url).netloc
        spider_template = "spider.tmpl"
        test_template = "test.tmpl"
        if "legistar.com" in domain:
            proto = "https" if start_url.startswith("https") else "http"
            start_url = f"{proto}://{domain}"
            spider_template = "spider_legistar.tmpl"
            test_template = "test_legistar.tmpl"
            fixture_file = self._gen_legistar_fixtures(name, start_url)
        else:
            fixture_file = self._gen_fixtures(name, start_url)
        classname = f"{string.capwords(name, sep='_').replace('_', '')}Spider"
        self._genspider(name, agency, classname, domain, start_url, spider_template)
        self._gen_tests(name, classname, start_url, fixture_file, test_template)

    def _genspider(self, name, agency, classname, domain, start_url, template_file):
        """Create spider from custom template"""
        template_dict = {
            "name": name,
            "agency": agency,
            "domain": domain,
            "start_url": start_url,
            "classname": f"{string.capwords(name, sep='_').replace('_', '')}Spider",
        }
        spider_file = f"{join(self.spiders_dir, name)}.py"
        shutil.copyfile(join(self.templates_dir, template_file), spider_file)
        render_templatefile(spider_file, **template_dict)
        logger.info(f"Created file: {spider_file}")

    def _gen_tests(self, name, classname, start_url, fixture_file, template_file):
        """Creates tests from test template file"""
        template_dict = {
            "name": name,
            "classname": classname,
            "fixture_file": fixture_file,
            "date_str": datetime.now().strftime("%Y-%m-%d"),
        }
        if "legistar" not in name:
            template_dict["start_url"] = start_url
        test_file = join(self.tests_dir, f"test_{name}.py")
        shutil.copyfile(join(self.templates_dir, template_file), test_file)
        render_templatefile(test_file, **template_dict)
        logger.info(f"Created file: {test_file}")

    def _gen_fixtures(self, name, start_url):
        """Creates fixures from HTML response at the start URL"""
        res = requests.get(start_url, headers={"user-agent": USER_AGENT})
        content = res.text.strip()
        fixture_file = join(self.fixtures_dir, f"{name}.html")
        with open(fixture_file, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Created file: {fixture_file}")
        return f"{name}.html"

    def _gen_legistar_fixtures(self, name, start_url):
        """Creates fixtures from a Legistar response"""
        events = []
        les = LegistarEventsScraper()
        les.BASE_URL = start_url
        les.EVENTSPAGE = f"{start_url}/Calendar.aspx"
        for event, _ in les.events(since=datetime.today().year):
            events.append((dict(event), None))
        fixture_file = join(self.fixtures_dir, f"{name}.json")
        with open(fixture_file, "w", encoding="utf-8") as f:
            json.dump(events, f)
        logger.info(f"Created file: {fixture_file}")
        return f"{name}.json"

    @property
    def spiders_dir(self):
        if self.settings.get("NEWSPIDER_MODULE"):
            spiders_module = import_module(self.settings["NEWSPIDER_MODULE"])
            spiders_dir = abspath(dirname(spiders_module.__file__))
        else:
            spiders_dir = "."
        return spiders_dir

    @property
    def templates_dir(self):
        return join(dirname(dirname(abspath(__file__))), "templates")

    @property
    def tests_dir(self):
        if self.spiders_dir == ".":
            return "."
        return join(dirname(dirname(self.spiders_dir)), "tests")

    @property
    def fixtures_dir(self):
        if self.tests_dir == ".":
            return "."
        return join(self.tests_dir, "files")
