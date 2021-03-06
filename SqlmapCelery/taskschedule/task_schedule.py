#!/ usr/bin/env
# coding=utf-8
#
# Copyright 2019 ztosec & https://sec.zto.com/
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
"""
author: b5mali4
To use:
>>> sq = Square(3)
>>> sq.area     
"""
import os
import signal
import json
import time
import subprocess
from sys import version_info
from common import log
from subprocess import Popen
from common.http_util import header_to_lowercase
from common.http_util import header_to_str
from common.http_util import json_to_urlencoded
from common.plugins_util import load_default_checkers, modify_default_checkers
from common.settings import DEFAULT_CONTENT_TYPE
from common.settings import FORM_DATA_CONTENT_TYPE
from common.settings import JSON_TEXT_CONTENT_TYPE
from plugins.base.vuln_enum import PluginSwith
from common.plugin_config.localfile_plugin_config import LocalFilePluginConfig
from argparse import Namespace

if version_info < (3, 0):
    IS_WIN = subprocess.mswindows
else:
    IS_WIN = subprocess._mswindows

logger = log.get_default_logger()


def modify_checker(broadcast):
    """
    修改本地插件配置信息，只修改本地配置文件

    {"type": "plugin", "action": "modify", "data": {"name": checker_name, "switch": PluginSwith.ON}
    :param broadcast: 
    :return: 
    """
    checker_name = broadcast["data"]["name"]
    switch = broadcast["data"]["switch"]
    checkers_dict = load_default_checkers()
    if checker_name in checkers_dict:
        logger.info('接收到修改插件{}状态为{}的请求'.format(checker_name, switch))
        LocalFilePluginConfig().modify_plugin_config(checker_name, "useable", switch)
        modify_default_checkers()


def scan(package, task_id, create_user, status):
    """
    :param package: 
    :param task_id: 
    :param create_user: 
    :param status: 
    :return: 
    """
    logger.info("hunter task has started")
    # 加载插件，只有一个插件
    checkers = load_default_checkers()
    logger.info('loading package success')
    logger.info('loading plugin success')
    try:
        if checkers["sqlmap"].useable == PluginSwith.ON:
            sqlmap_process = SqlmapProcess(package, task_id)
            sqlmap_process.engine_start()
            while not sqlmap_process.engine_has_terminated() and sqlmap_process.process is not None:
                logger.info("sqlmap program is runing")
                time.sleep(5)
            sqlmap_process.engine_kill()
            logger.warn("sqlmap program runs to completion")
    except KeyboardInterrupt as e:
        logger.exception("scan error")
    finally:
        logger.info("hunter task has done")


class SqlmapProcess():
    def __init__(self, package, task_id):
        self.process = None
        self.package = package
        self.task_id = task_id

    def parse_package(self):
        """
        将从mq中获得的数据解析 ,sqlmap会自动解析参数，json还是普通data
        :return: 
        """
        header = None
        cookie = None
        url = self.package['url'] if "url" in self.package else None

        if "headers" in self.package:
            header = header_to_lowercase(json.loads(self.package["headers"]))
            if "Cookie" in json.loads(self.package["headers"]):
                cookie = json.loads(self.package["headers"])['Cookie']
        if header:
            header = header_to_str(header)
        data = self.parse_data(self.package, header)
        return url, data, cookie, header

    def parse_data(self, package, header):
        """
        根据请求头解析数据
        :param package: 
        :param header: 
        :return: 
        """

        result = None

        if "data" not in package or package["data"] == "":
            return result

        if header and "content-type" in header:
            if FORM_DATA_CONTENT_TYPE in header["content-type"] or DEFAULT_CONTENT_TYPE in header["content-type"]:
                return json_to_urlencoded(json.loads(package['data']))
            elif JSON_TEXT_CONTENT_TYPE in header["content-type"]:
                return str(json.loads(package["data"]))
        return json_to_urlencoded(json.loads(package['data']))

    def get_command(self):
        """
        根据数据的得到命令,超时重联3次
        :return: 
        """
        command = self.init_command_by_path()
        # status = True
        #  表示不正常，比如一个数据包中没有url
        url, data, cookie, headers = self.parse_package()
        if url is None or url == "":
            return False, command
        command += ["--url", "{}".format(url)]
        if data is not None and data != "":
            command += ["--data", "{}".format(data)]
        if cookie is not None and cookie != "":
            command += ["--cookie", "{}".format(cookie)]
        if headers is not None and headers != "":
            command += ["--headers", "{}".format(headers)]
        command += ["--batch"]
        command += ["--purge-output"]
        # print (" ".join(command))
        return True, command

    def init_command_by_path(self):
        """
        根据路径
        :return: 
        """
        from common.path import SQLMAP_SCRIPT_PATH
        command = ["python2", SQLMAP_SCRIPT_PATH]
        command += ["--celery", "{}".format(self.task_id)]
        return command

    def engine_start(self):
        """开始命令"""
        status, command = self.get_command()
        # print status, command
        if status:
            self.process = Popen(command, shell=False, close_fds=not IS_WIN)

    def engine_stop(self):
        """
        结束
        :return: 
        """
        if self.process:
            self.process.terminate()
            return self.process.wait()
        else:
            return None

    def engine_process(self):
        return self.process

    def engine_kill(self):
        """
        强制kill,删除SQLMAP扫描缓存记录
        :return: 
        """
        if self.process:
            try:
                self.process.kill()
                os.killpg(self._process.pid, signal.SIGTERM)
                return self.process.wait()
            except:
                pass
        return None

    def engine_get_id(self):
        """
        获得进程模块
        :return: 
        """
        if self.process:
            return self.process.pid
        else:
            return None

    def engine_get_returncode(self):
        """
        如果为None表示命令还在执行中，为0表示已经执行完成并退出
        :return: 
        """
        if self.process:
            self.process.poll()
            return self.process.returncode
        else:
            return None

    def engine_has_terminated(self):
        return isinstance(self.engine_get_returncode(), int)
