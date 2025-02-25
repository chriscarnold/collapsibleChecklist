# -*- coding: utf-8 -*-
"""
Macro that pulls a checklist template from a wiki page, and renders it as
a checklist instance in a ticket description box.

Implements the following trac extensions points (see
https://trac.edgewall.org/wiki/TracDev/PluginDevelopment/ExtensionPoints/):

 * IRequestHandler - Allows plugins to process HTTP requests
 * ITemplateProvider - Registers templates/static resources used by plugin
 * IEnvironmentSetupParticipant - Updates environment database for plugin use

"""

import re
import time
import json
import pkg_resources
from pkg_resources import resource_filename

from trac.core import implements, Component
from trac.env import IEnvironmentSetupParticipant
from trac.config import Option
from trac.db.api import DatabaseManager
from trac.db.schema import Table, Column

from trac.web.chrome import (
    ITemplateProvider,
    add_stylesheet,
    add_script,
    add_script_data,
)
from trac.web.api import IRequestHandler, IRequestFilter

from trac.wiki.macros import WikiMacroBase
from trac.wiki.model import WikiPage
from trac.wiki.formatter import format_to_html
from trac.util.html import Markup, tag

# database schema version / updates (stored in "system" table)
PLUGIN_NAME = "TracChecklist"
PLUGIN_VERSION = 1


class ChecklistMacro(WikiMacroBase):
    """Insert checklist instance sourced from wiki page template."""

    _description = "Insert checklist instance sourced from wiki page template."

    # trac.ini option for wiki page below which all templates are found
    _root = Option(
        "checklist",
        "template_root",
        default="TracChecklist",
        doc="root wiki page for checklist templates",
    )

    implements(ITemplateProvider)

    def parse_macro(self):
        """Not used (included to satisfy abstract class requirement)"""
        pass

    def get_htdocs_dirs(self):
        """directories where static files are located"""
        return [("checklist", resource_filename(__name__, "htdocs"))]

    def get_templates_dirs(self):
        """directories where html templates are located."""
        return [resource_filename(__name__, "htdocs")]

    def insert_checkboxes(self, html, status):
        """Convert [x] placeholders to html checkboxes

        Steps start with [x] and end with \\ in wiki markdown,
        which converts to <br /> after html formatting:
            [x] something to do ... <br />

        Args:
            html    (STR): checklist template wiki page converted to html
            status (DICT): step is checked if included in this dictionary

        Returns:
            html (STR): checklist instance with html checkboxes
        """
        # Log the incoming HTML
        self.env.log.debug("INSERT_CHECKBOXES - INCOMING HTML: %s", html)

        # find all steps
        regex = r"(?=\[x])(.*?)(?<=<br \/>)"
        steps = re.findall(regex, html)

        # Log the steps found
        self.env.log.debug("INSERT_CHECKBOXES - FOUND STEPS: %s", steps)

        # insert checkbox tags
        box_idx = 0
        for step in steps:
            box_idx = box_idx + 1
            box_name = "step_%d" % box_idx
            box_label = step[4:]
            box_label = box_label.replace(u'\u200b', "")
            box_status = ""
            if box_name in status.keys():
                box_status = "checked"

            box_html = Markup(
                (
                    '<label class="container">'
                    '<input type="checkbox" name="{}" value="done" {} />{}'
                    '<span class="checkmark"></span>'
                    "</label>"
                ).format(box_name, box_status, box_label)
            )
            # Log each replacement
            self.env.log.debug("INSERT_CHECKBOXES - Replacing '%s' with '%s'", step, box_html)
            html = html.replace(step, box_html)

        self.env.log.debug("INSERT_CHECKBOXES - Final HTML: %s", html)

        return html

    def expand_macro(self, formatter, name, content):
        """Expand the macro into the requested checklist instance.

        self.env    : https://trac.edgewall.org/browser/trunk/trac/env.py
        self.config : https://trac.edgewall.org/browser/trunk/trac/config.py

        formatter.resource.realm : wiki, ticket, etc.
        formatter.resource.id    : id of the ticket calling the macro
        formatter.href           : url info (base, path_safe, etc.)
        formatter.wiki           : https://trac.edgewall.org/browser/trunk/trac/wiki/api.py
        formatter.context        : metadata on the called page with the macro in it
        formatter.req            : web request that called the page with the macro

        name     : name of the macro being called (Checklist)
        content  : name of checklist template (wiki page) from macro argument
        """

        # get checklist instance states (JSON encoded checkbox status)
        box_status = {}
        with self.env.db_query as db_query:
            query = (
                "SELECT status FROM checklist WHERE "
                + "realm = %s AND resource  = %s AND checklist = %s "
            )
            param = [formatter.resource.realm, formatter.resource.id, content]

            cursor = db_query.cursor()
            cursor.execute(query, param)
            row = cursor.fetchone()
            if row:
                box_status = json.loads(row[0])

        # get checklist template (wiki page)
        cname = str(self._root) + "/" + content
        cname = cname.replace("//", "/")
        page = WikiPage(self.env, cname)
        if not page.exists:
            err_msg = "CHECKLIST ERROR: \n template '" + cname + "' does not exist."
            return err_msg

        # strip header (if exists), convert to html, insert checkboxes
        # header is separated with horizontal line: ----
        wiki = page.text
        line = re.search("(?<!-)----(?!-)", wiki)
        if line:
            wiki = wiki[line.end() + 1 :]
        html = format_to_html(self.env, formatter.context, wiki)
        html = self.insert_checkboxes(html, box_status)

        # create the checklist form
        # dest = formatter.req.href('/checklist/update')
        # form = "<form class='checklist' method='post' action='"+dest+"'> \n"
        form = tag.form(
            action=formatter.req.href("/checklist/update"),
            class_="checklist",
            method="post",
        )

        # checklist header (template info)
        href = formatter.req.href("/wiki/" + cname)
        head = tag.div("TracChecklist: ", tag.a(cname, href=href), class_="source")

        # checklist footer / form
        backpath = formatter.req.href(formatter.req.path_info)
        form_token = formatter.req.form_token
        realm = str(formatter.resource.realm)
        resource = str(formatter.resource.id)
        checklist = str(content)
        foot = tag(
            tag.input(type="hidden", name="__backpath__", value=backpath),
            tag.input(type="hidden", name="__FORM_TOKEN", value=form_token),
            tag.input(type="hidden", name="realm", value=realm),
            tag.input(type="hidden", name="resource", value=resource),
            tag.input(type="hidden", name="checklist", value=checklist),
            tag.input(type="submit", class_="button", value="Save Checklist"),
        )

        # add stylesheet definitions to the page
        # note pattern is 'checklist/filename.ext' (no htdocs dir)
        add_stylesheet(formatter.req, "checklist/checklist.css")

        # return the final output
        form.append([head, html, foot])
        return form


class ChecklistUpdate(Component):
    """Handles item check off and instance saving.

    Implements the following trac extensions point: IRequestHandler
    https://trac.edgewall.org/wiki/TracDev/PluginDevelopment/ExtensionPoints/
    """

    _description = "Handles checklist updates, submit & save."
    implements(IRequestHandler)

    def match_request(self, req):
        """determines if request was a form update/save"""
        match = req.path_info.endswith("checklist/update")
        return match

    def process_request(self, req):
        """saves updated checklist state to the database."""

        try:
            # get form data and new status as JSON string
            args = dict(req.args)
            backpath = args["__backpath__"]
            realm = args["realm"]
            resource = args["resource"]
            checklist = args["checklist"]
            steps = {k: v for k, v in args.iteritems() if k.startswith("step")}
            status = json.dumps(steps)

            # save to db
            query = (
                "REPLACE INTO checklist (realm,resource,checklist,status) "
                + "VALUES (%s, %s, %s, %s)"
            )
            param = [realm, resource, checklist, status]

            self.env.db_transaction(query, param)
            form_buffer = "OK"

            if backpath is not None:
                req.send_response(302)
                req.send_header("Content-Type", "text/plain")
                req.send_header("Location", backpath)
                req.send_header("Content-Length", str(len(form_buffer)))
                req.end_headers()
                req.write(form_buffer)
            else:
                req.send_response(200)
                req.send_header("Content-Type", "text/plain")
                req.send_header("Content-Length", str(len(form_buffer)))
                req.end_headers()
                req.write(form_buffer)

        except Exception as error:
            form_buffer = "ERROR:" + str(error)
            req.send_response(500)
            req.send_header("Content-type", "text/plain")
            req.send_header("Content-Length", str(len(form_buffer)))
            req.end_headers()
            req.write(form_buffer)


class ChecklistInsert(Component):
    """Adds dropdown selector in ticket description edit box to insert a checklist."""

    _description = (
        "Adds dropdown selector in ticket description edit box to insert a checklist."
    )
    implements(ITemplateProvider, IRequestFilter)

    def get_htdocs_dirs(self):
        """directories where static files are located"""
        return [("checklist", resource_filename(__name__, "htdocs"))]

    def get_templates_dirs(self):
        """directories where html templates are located."""
        return [resource_filename(__name__, "htdocs")]

    def pre_process_request(self, req, handler):
        """Not used (included to satisfy abstract class requirement)"""
        return handler

    def post_process_request(self, req, template, data, metadata):
        """Adds checklist drop-down selector in ticket description edit box.

        Args:
            req      (obj): web request object
            template (str): web template that called this function
            data     (obj): ticket attributes
            metadata (obj): ticket attributes

        Returns:
            template (str): unchanged from input
            data     (obj): unchanged from input
            metadata (obj): unchanged from input
        """
        # only alter specific ticket templates
        self.log.debug("TracChecklist #### template: %s", template)
        if template in ["ticket.html"]:
            # list of available checklist templates (pages) under root wiki page
            templates = []
            root = Option(
                "checklist",
                "template_root",
                default="TracChecklist",
                doc="wiki page root for checklist templates",
            )
            root = self.config.get("checklist", "template_root")
            query = "SELECT name FROM wiki WHERE version = 1 AND name LIKE %s"
            param = ["%" + root + "%"]

            with self.env.db_query as db_query:
                cursor = db_query.cursor()
                cursor.execute(query, param)
                # self.log.debug(cursor._executed)
                for row in cursor.fetchall():
                    if row[0] != root:
                        templates.append(row[0].replace(root + "/", ""))

            # add new ticket components (CSS, jquery, template list)
            add_stylesheet(req, "checklist/menu.css")
            add_script_data(req, {"templates": templates})
            add_script(req, "checklist/menu.js")

        return (template, data, metadata)


class ChecklistSetup(Component):
    """Handles environment upgrades / setup."""

    _description = "Handles environment setup / upgrades."
    implements(IEnvironmentSetupParticipant)

    def environment_created(self):
        """Create the required table for this environment."""
        self.log.info("creating environment for TracChecklist plugin.")
        # Same work is done for environment created and upgraded
        self.upgrade_environment()

    def environment_needs_upgrade(self):
        """Determine if environment database needs to be upgraded.

        Returns:
            BOOL: true if upgrade is needed
        """
        dbm = DatabaseManager(self.env)
        ver = dbm.get_database_version(PLUGIN_NAME)
        needs_upgrade = dbm.needs_upgrade(PLUGIN_VERSION, PLUGIN_NAME)
        self.log.debug(
            "TracChecklist plugin v%s - upgrade needed: %s", ver, needs_upgrade
        )
        if needs_upgrade:
            self.log.info("environment requires upgrade for TracChecklist plugin.")
        return needs_upgrade

    def upgrade_environment(self):
        """Upgrade environment database as needed."""

        dbm = DatabaseManager(self.env)
        ver = dbm.get_database_version(PLUGIN_NAME)
        self.log.info(
            "upgrading environment for TracChecklist plugin from v%s to v%s.",
            ver,
            PLUGIN_VERSION,
        )

        # check if this is first use (table does not exist)
        if ver == 0:
            # create the database checklist table
            schema = [
                Table("checklist", key=("realm", "resource", "checklist"))[
                    Column("realm", type="text"),
                    Column("resource", type="text"),
                    Column("checklist", type="text"),
                    Column("status", type="text"),
                ]
            ]

            self.log.info("creating checklist table ...")
            dbm.create_tables(schema)

            # create the wiki root page from file
            page = str(pkg_resources.resource_string(__name__, "plugin.wk"))
            timestamp = int(time.time() * 1000000)
            query = "INSERT INTO wiki (name, version, time, author, text) "
            query += "VALUES ('TracChecklist', 1, %s, 'trac', %s)"
            self.log.info("creating checklist wiki root ...")
            self.env.db_transaction(query, (timestamp, page))

            # update version number in the 'system' table for this plugin
            dbm.set_database_version(PLUGIN_VERSION, PLUGIN_NAME)

        else:
            dbm.upgrade(PLUGIN_VERSION, PLUGIN_NAME, "checklist.upgrades")
