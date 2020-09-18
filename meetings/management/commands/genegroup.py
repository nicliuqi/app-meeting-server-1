import requests
import lxml
import time
import logging
from lxml.etree import HTML
from meetings.models import Group
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    logger = logging.getLogger('log')

    def handle(self, *args, **options):
        t1 = time.time()
        self.logger.info('Starting to genegroup...')
        url = 'https://gitee.com/openeuler/community/tree/master/sig'
        r = requests.get(url)
        html = HTML(r.content)
        assert isinstance(html, lxml.etree._Element)
        sigs_list = []
        i = 3
        while True:
            sig_name = html.xpath("//div[@id='tree-slider']/div[{}]/div[1]/a/@title".format(i))[0]
            sig_page = html.xpath("//div[@id='tree-slider']/div[{}]/div[1]/a/@href".format(i))[0]
            etherpad = 'https://etherpad.openeuler.org/p/{}-meetings'.format(sig_name)
            if sig_name == 'sigs.yaml':
                break
            i += 2
            if sig_name == 'sig-template':
                continue
            # 获取所有sig的名称、首页和etherpad
            sigs_list.append([sig_name, 'https://gitee.com' + sig_page, etherpad])

        sigs_list = sorted(sigs_list)
        t2 = time.time()
        self.logger.info('Has got sigs_list, wasted time: {}'.format(t2 - t1))

        # 获取所有owner对应sig的字典owners_sigs
        # 定义owners集合
        owners = set()
        owners_sigs = {}
        for sig in sigs_list:
            url = 'https://gitee.com/openeuler/community/blob/master/sig/{}/OWNERS'.format(sig[0])
            r = requests.get(url)
            html = HTML(r.text)
            assert isinstance(html, lxml.etree._Element)
            res = html.xpath('//div[@class="line"]/text()')
            for i in res[1:]:
                maintainer = i.strip().split('-')[-1].strip()
                owners.add(maintainer)
        # 去除owners中为''的元素
        owners.remove('')
        # 初始化owners_sigs
        for owner in owners:
            owners_sigs[owner] = []
        # 遍历sigs_list,添加在该sig中的owner所对应的sig
        for sig in sigs_list:
            url = 'https://gitee.com/openeuler/community/blob/master/sig/{}/OWNERS'.format(sig[0])
            r = requests.get(url)
            html = HTML(r.text)
            assert isinstance(html, lxml.etree._Element)
            res = html.xpath('//div[@class="line"]/text()')
            # 获取每个sig的maintainer的列表
            maintainers = []
            for i in res[1:]:
                maintainer = i.strip().split('-')[-1].strip()
                maintainers.append(maintainer)
            for owner in owners:
                if owner in maintainers:
                    owners_sigs[owner].append(sig[0])
        t3 = time.time()
        self.logger.info('Has got owners_sigs, wasted time: {}'.format(t3 - t2))

        for sig in sigs_list:
            # 获取邮件列表
            r = requests.get(sig[1])
            html = HTML(r.text)
            assert isinstance(html, lxml.etree._Element)
            try:
                maillist = html.xpath('//li[contains(text(), "邮件列表")]/a/@href')[0].replace('mailto:', '')
            except IndexError:
                try:
                    maillist = html.xpath('//a[contains(text(), "邮件列表")]/@href')[0].rstrip('/').split('/')[-1].replace('mailto:', '')
                except IndexError:
                    maillist = 'dev@openeuler.org'
            if not maillist:
                maillist = 'dev@openeuler.org'
            sig.append(maillist)

            # 获取IRC频道
            try:
                irc = html.xpath('//a[contains(text(), "IRC频道")]/@href')[0]
            except IndexError:
                try:
                    irc = html.xpath('//a[contains(text(), "IRC")]/@href')[0]
                except IndexError:
                    try:
                        irc = html.xpath('//*[contains(text(), "IRC")]/text()')[0].split(':')[1].strip().rstrip(')')
                    except IndexError:
                        irc = '#openeuler-dev'
            if '#' not in irc:
                irc = '#openeuler-dev'
            sig.append(irc)

            # 获取owners
            url = 'https://gitee.com/openeuler/community/blob/master/sig/{}/OWNERS'.format(sig[0])
            r = requests.get(url)
            html = HTML(r.text)
            assert isinstance(html, lxml.etree._Element)
            res = html.xpath('//div[@class="line"]/text()')
            owners = []
            for i in res[1:]:
                maintainer = i.strip().split('-')[-1].strip()
                r = requests.get('https://gitee.com/api/v5/users/{}'.format(maintainer))
                owner = {}
                if r.status_code == 200:
                    owner['gitee_id'] = maintainer
                    owner['avatar_url'] = r.json()['avatar_url']
                    owner['home_page'] = 'https://gitee.com/{}'.format(maintainer)
                    owner['sigs'] = owners_sigs[maintainer]
                    if r.json()['email']:
                        owner['email'] = r.json()['email']
                if r.status_code == 404:
                    pass
                owners.append(owner)
            sig.append(owners)
            sig[5] = str(sig[5]).replace("'", '"')
            group_name = sig[0]
            home_page = sig[1]
            etherpad = sig[2]
            maillist = sig[3]
            irc = sig[4]
            owners = sig[5]
            # 查询数据库，如果sig_name不存在，则创建sig信息；如果sig_name存在,则更新sig信息
            if not Group.objects.filter(group_name=group_name):
                Group.objects.create(group_name=group_name, home_page=home_page, maillist=maillist,
                                     irc=irc, etherpad=etherpad, owners=owners)
                self.logger.info("Create sig: {}".format(group_name))
                self.logger.info(sig)
            else:
                Group.objects.filter(group_name=group_name).update(maillist=maillist, irc=irc, etherpad=etherpad, owners=owners)
                self.logger.info("Update sig: {}".format(group_name))
                self.logger.info(sig)
        t4 = time.time()
        self.logger.info('Has updated database, wasted time: {}'.format(t4 - t3))
        self.logger.info('All done. Wasted time: {}'.format(t4 - t1))
