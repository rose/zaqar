# Copyright (c) 2013 Rackspace Hosting, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""wsgi transport helpers."""

import uuid

import falcon
import six

from zaqar import context
from zaqar.i18n import _
import zaqar.openstack.common.log as logging
from zaqar.transport import validation


LOG = logging.getLogger(__name__)


def get_client_uuid(req):
    """Read a required Client-ID from a request.

    :param req: A falcon.Request object
    :raises: HTTPBadRequest if the Client-ID header is missing or
        does not represent a valid UUID
    :returns: A UUID object
    """

    try:
        return uuid.UUID(req.get_header('Client-ID', required=True))

    except ValueError:
        description = _(u'Malformed hexadecimal UUID.')
        raise falcon.HTTPBadRequest('Wrong UUID value', description)


def extract_project_id(req, resp, params):
    """Adds `project_id` to the list of params for all responders

    Meant to be used as a `before` hook.

    :param req: request sent
    :type req: falcon.request.Request
    :param resp: response object to return
    :type resp: falcon.response.Response
    :param params: additional parameters passed to responders
    :type params: dict
    :rtype: None
    """
    params['project_id'] = req.get_header('X-PROJECT-ID')
    if params['project_id'] == "":
        raise falcon.HTTPBadRequest('Empty project header not allowed',
                                    _(u'''
X-PROJECT-ID cannot be an empty string. Specify the right header X-PROJECT-ID
and retry.'''))

    # TODO(flaper87): Make version comparison smarter to support v2.
    if not params['project_id'] and 'v1.1' in req.path:
        raise falcon.HTTPBadRequest('Project-Id Missing',
                                    _(u'The header X-PROJECT-ID was missing'))


def require_client_id(req, resp, params):
    """Makes sure the header `Client-ID` is present in the request

    Use as a before hook.
    :param req: request sent
    :type req: falcon.request.Request
    :param resp: response object to return
    :type resp: falcon.response.Response
    :param params: additional parameters passed to responders
    :type params: dict
    :rtype: None
    """

    if 'v1.1' in req.path:
        # NOTE(flaper87): `get_client_uuid` already raises 400
        # it the header is missing.
        get_client_uuid(req)


def validate_queue_identification(validate, req, resp, params):
    """Hook for validating the queue name and project id in requests.

    The queue name validation is short-circuited if 'queue_name' does
    not exist in `params`.

    This hook depends on the `get_project` hook, which must be
    installed upstream.


    :param validate: A validator function that will
        be used to check the queue name against configured
        limits. functools.partial or a closure must be used to
        set this first arg, and expose the remaining ones as
        a Falcon hook interface.
    :param req: Falcon request object
    :param resp: Falcon response object
    :param params: Responder params dict
    """

    try:
        validate(params['queue_name'],
                 params['project_id'])
    except KeyError:
        # NOTE(kgriffs): queue_name not in params, so nothing to do
        pass
    except validation.ValidationFailed:
        project = params['project_id']
        queue = params['queue_name']
        if six.PY2:
            queue = queue.decode('utf-8', 'replace')

        LOG.debug(u'Invalid queue name "%(queue)s" submitted for '
                  u'project: %(project)s',
                  {'queue': queue, 'project': project})

        raise falcon.HTTPBadRequest(_(u'Invalid queue identification'),
                                    _(u'The format of the submitted queue '
                                      u'name or project id is not valid.'))


def require_accepts_json(req, resp, params):
    """Raises an exception if the request does not accept JSON

    Meant to be used as a `before` hook.

    :param req: request sent
    :type req: falcon.request.Request
    :param resp: response object to return
    :type resp: falcon.response.Response
    :param params: additional parameters passed to responders
    :type params: dict
    :rtype: None
    :raises: falcon.HTTPNotAcceptable
    """
    if not req.client_accepts('application/json'):
        raise falcon.HTTPNotAcceptable(
            u'''
Endpoint only serves `application/json`; specify client-side
media type support with the "Accept" header.''',
            href=u'http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html',
            href_text=u'14.1 Accept, Hypertext Transfer Protocol -- HTTP/1.1')


def inject_context(req, resp, params):
    """Inject context value into request environment.

    :param req: request sent
    :type req: falcon.request.Request
    :param resp: response object
    :type resp: falcon.response.Response
    :param params: additional parameters passed to responders
    :type params: dict
    :rtype: None

    """
    client_id = req.get_header('Client-ID')
    project_id = params.get('project_id', None)

    ctxt = context.RequestContext(project_id=project_id,
                                  client_id=client_id)
    req.env['zaqar.context'] = ctxt
