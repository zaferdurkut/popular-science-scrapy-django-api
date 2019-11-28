import math
import scrapy
import logging

from slugify import slugify

from scrapy import signals

from urllib.parse import (
    urlsplit,
    parse_qsl,
    urlunparse,
    urlencode,
    unquote,
)

from django.utils.timezone import now
import urllib

from config.listoverview_selectors import listoverview_selectors, last_page_selector
from api.models import ListOverview, CommandLog
from crawler.items import ListOverview
from config.pages import pages

__all__ = ['CrawlJobSpider']

class CommandLogger(object):
    STATUS_FAIL = "FAIL"
    STATUS_OK = "OK"

    @staticmethod
    def add(**kwargs):
        logItem = CommandLog(
            name=kwargs.get('name', None),
            type=kwargs.get('type', None),
            started_at=kwargs.get('started_at', None),
            ended_at=kwargs.get('ended_at', None),
            status=kwargs.get('status', None),
            message=kwargs.get('message', None)
        )
        logItem.save()
        return logItem

    @staticmethod
    def update(logId, **kwargs):
        logItem = CommandLog.objects.filter(id=logId).first()
        logItem.ended_at = kwargs.get('ended_at', None)
        logItem.status = kwargs.get('status', None)
        logItem.message = kwargs.get('message', None)
        logItem.save()
        return logItem

    @staticmethod
    def get(logId):
        logItem = CommandLog.objects.filter(id=logId).first()
        return logItem


class LoggedScrapySpider(scrapy.Spider):
    _commandLogItem = None
    _commandLogMessage = ""
    failed_urls = []

    def start_requests(self):
        self._commandLogItem = CommandLogger.add(
            name=self.name,
            started_at=now(),
            type='spider',
            status=""
        )

    def spider_closed(self, spider, reason):
        logMessage = "\n" + str(len(spider.failed_urls)) + " failed urls.\n "
        if len(spider.failed_urls):
            logMessage += str(spider.failed_urls)

        self._commandLogItem.message = self._commandLogMessage + logMessage
        self._commandLogItem.status = "OK"
        self._commandLogItem.ended_at = now()
        self._commandLogItem.save()


class CrawlJobSpider(LoggedScrapySpider):
    """
    name: CrawlJobSpider
    desc: Base class for crawl job spiders
    auth: mustafa.ileri@zingat.com
    """

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(CrawlJobSpider, cls).from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)

        return spider

    def start_requests(self):
        """
        Get jobs from crawl_jobs where crawl status is waiting
        """

        # @todo: move logger to better method
        super(CrawlJobSpider, self).start_requests()

        crawl_jobs = pages['first']

        for crawl_job in crawl_jobs:
            crawl_job.crawl_status = CrawlStatus.IN_PROGRESS
        CrawlJob.objects.bulk_update(crawl_jobs, update_fields=['crawl_status'])  # updates only name column
        self._commandLogMessage += str(crawl_jobs.count()) + " crawljob objects progressed."

        i = 0
        total = len(crawl_jobs)

        for crawl_job in crawl_jobs:
            i += 1

            stat_key = 'crawl_job_' + str(crawl_job.id)

            crawl_job_info = self.crawler.stats.get_value(stat_key, dict(
                crawled_listings=0,
            ))

            self.crawler.stats.set_value(stat_key, crawl_job_info)
            request = scrapy.Request(
                callback=self.parse,
                url=crawl_job.url,
                meta=CrawlJobSpider.get_meta_data(crawl_job),
                errback=self.errback,
            )

            if i % 10 == 0:
                self.logger.info('CrawlJob: %d url sent to the queue. (at %d), %s' % (i, total, crawl_job.url))

            yield request

    def parse(self, response):
        """
        Creating a stat record for crawl job and parsing all pages
        :param response: 
        :return: 
        """

        if response.status != 200:
            self.logger.info('Url is not 200: %s , %d' % (response.request.url, response.status))

        selectors = self.selectors
        listing_count = CrawlerUtils.clean_listing_count(response.css(selectors.get('listing_count')).extract_first())

        stat_item = StatItem(
            total_listing_count=listing_count,
            crawled=False,
            crawl_start_date=now(),
            crawl_job=response.meta['crawl_job'],
        )

        if 'stat' not in response.meta:
            response.meta['stat'] = stat_item.save()

        provider_parameters = response.meta['crawl_job'].provider.providerparameter_set.first()

        if 'filtered_pages' not in response.meta:
            response.meta['filtered_pages'] = True

        if listing_count > provider_parameters.max_item_limit and response.meta.get(
                'filtered_pages') and self.provider_id != ProviderHelper.ZINGAT.value:
            filtered_urls, around_number = self.get_filtered_pages(
                response,
                provider_parameters,
                listing_count
            )

            response.meta['filtered_pages'] = False if 2 >= around_number else True

            for filtered_url in filtered_urls:
                if self.provider_id == ProviderHelper.ZINGAT.value:
                    filtered_url = self.replace_filtered_url(filtered_url)

                request = scrapy.Request(
                    url=filtered_url,
                    callback=self.parse,
                    meta=response.meta,
                    dont_filter=True,
                    errback=self.errback,
                )
                self.logger.info('Filtered Url: %s , %d' % (filtered_url, around_number))
                yield request
        elif listing_count != 0:
            # Pagination parse
            pages = CrawlerUtils.calculate_pagination_urls(
                response.request.url,
                response.meta['paginationParameters'],
                listing_count,
            )

            response.meta['total_page'] = len(pages)

            for i, page in enumerate(pages, 1):
                response.meta['page_number'] = i
                response.meta['page'] = page

                request = scrapy.Request(
                    url=page,
                    callback=self.parse_pagination,
                    meta=response.meta,
                    dont_filter=True,
                    errback=self.errback,
                )

                request.headers['Upgrade-Insecure-Requests'] = 1

                yield request
        elif listing_count == 0:
            stat = response.meta['stat']
            stat.crawled = True
            stat.save()

            # change crawl_job table crawl status
            crawl_job = stat.crawl_job
            crawl_job.crawl_status = CrawlStatus.FINISHED
            crawl_job.save()

    def parse_pagination(self, response):
        """
        Parsing ListOverviews on page[n]
        :param response: 
        :return: 
        """

        selectors = self.selectors
        list_overviews = response.css(selectors.get('list_container'))
        valid_info_headers = self.get_valid_info_headers(response)
        featured = {
            response.request.url: self.is_available_featured(response, selectors['featured'])
        }

        list_overviews = self.get_cleaned_list_overviews(list_overviews)
        for list_overview in list_overviews:
            pass

