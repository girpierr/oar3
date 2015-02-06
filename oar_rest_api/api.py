# -*- coding: utf-8 -*-
from __future__ import with_statement, absolute_import

import sys
import json
from math import ceil
from collections import OrderedDict
from functools import wraps

from flask import Blueprint, Response, abort, current_app, request, url_for, g
from oar.lib.compat import reraise, to_unicode, iteritems
from oar.lib.database import BaseQuery, BaseModel

from .utils import JSONEncoder, get_utc_timestamp


class API(Blueprint):

    def __init__(self, *args, **kwargs):
        version = kwargs.pop("version", None)
        super(API, self).__init__(*args, **kwargs)
        self.version = version if version is not None else self.name
        self.before_request(self.prepare_response)


    def route(self, rule, args={}, **options):
        """A decorator that is used to define custom routes, injects parsed
        arguments into a view function or method and jsonify the response.

        Example usage with: ::

            @api.route('/hello', methods=['get', 'post'], args={'name': str})
            def greet(name="world"):
                return {'message': 'Hello ' + name}

        """
        parent_method = super(API, self).route
        def decorator(f):
            @wraps(f)
            def decorated(*proxy_args, **proxy_kwargs):
                if args:
                    parser = ArgParser(args)
                    parsed_kwargs = parser.parse()
                    proxy_kwargs.update(parsed_kwargs)
                result = f(*proxy_args, **proxy_kwargs)
                if result is None:
                    result = {}
                if isinstance(result, (dict, list, BaseModel)):
                    return self._json_response(result)
                return result
            parent_method(rule, **options)(decorated)
            parent_method(rule + ".json", **options)(decorated)
        return decorator

    def prepare_response(self):
        g.data = OrderedDict()
        g.data['api_timezone'] ='UTC'
        g.data['api_timestamp'] = get_utc_timestamp()

    def _json_dumps(self, obj, **kwargs):
        """Dumps object to json string. """
        kwargs.setdefault('ensure_ascii', False)
        kwargs.setdefault('cls', JSONEncoder)
        kwargs.setdefault('indent', 4)
        kwargs.setdefault('separators', (',', ': '))
        kwargs.setdefault('encoding', 'utf-8')
        return json.dumps(obj, **kwargs)

    def _json_response(self, obj):
        """Get a json response. """
        return Response(self._json_dumps(obj),
                        mimetype='application/json')


class ArgParser(object):
    """Flask request argument parser."""

    DEFAULT_TARGETS = ('querystring', 'json', 'form')

    def __init__(self, argmap, targets):
        self.argmap = argmap
        self.missing = object()
        self.targets = targets or self.DEFAULT_TARGETS

    def get_value(self, data, name):
        return data.get(name, self.missing)

    def parse_value(self, name):
        """Pull a form value from the request."""
        for target in self.targets:
            if target == "querystring":
                value = self.get_value(request.args, name)
            elif target == "json":
                json_data = request.get_json(silent=True)
                if json_data:
                    value = self.get_value(json_data, name)
                else:
                    value = self.missing
            elif target == "form":
                value = self.get_value(request.form, name)
            if value is not self.missing:
                return value
        return self.missing

    def convert(self, value, argtype):
        if argtype == str:
            return to_unicode(value)
        else:
            return argtype(value)

    def parse(self):
        """Parses the request arguments."""
        kwargs = {}
        for argname, argtype in iteritems(self.argmap):
            value = self.parse_value(argname)
            if value is not self.missing:
                try:
                    kwargs[argname] = self.convert(value, argtype)
                except:
                    try:
                        abort(400)
                    except:
                        exc_type, exc_value, tb = sys.exc_info()
                        exc_value.data = \
                            ("The parameter '%s' specified in the request "
                            "URI is not supported." % argname)
                        reraise(exc_type, exc_value, tb.tb_next)
        return kwargs


class APIBaseQuery(BaseQuery):

    def get_or_404(self, ident):
        try:
            return self.get_or_error(ident)
        except:
            abort(404)

    def first_or_404(self):
        try:
            return self.first_or_error()
        except:
            abort(404)

    def paginate(self, offset, limit, error_out=True):
        if limit is None:
            limit = current_app.config.get("API_DEFAULT_MAX_ITEMS_NUMBER")
        if error_out and offset < 0:
            abort(404)
        items = self.limit(limit).offset(offset).all()
        if not items and offset != 0 and error_out:
            abort(404)
        # No need to count if we're on the first page and there are fewer
        # items than we expected.
        if offset == 0 and len(items) < limit:
            total = len(items)
            limit = total
        else:
            total = self.order_by(None).count()
        return Pagination(offset, limit, total, items)


class Pagination(object):
    """Internal helper class returned by :meth:`APIBaseQuery.paginate`."""

    def __init__(self, offset, limit, total, items):
        self.offset = offset
        self.limit = limit or 0
        self.total = total
        self.items = items

    @property
    def current_page(self):
        """The number of the current page (1 indexed)"""
        if self.limit > 0 and self.offset > 0:
            return int(ceil(self.offset / float(self.limit))) + 1
        return 1

    @property
    def pages(self):
        """The total number of pages"""
        if self.total > 0 and self.limit > 0:
            return int(ceil(self.total / float(self.limit)))
        return 1

    @property
    def has_next(self):
        """True if a next page exists."""
        return self.current_page < self.pages

    @property
    def next_url(self):
        if self.has_next:
            kwargs = {'offset': self.offset + self.limit, 'limit': self.limit}
            return url_for(request.endpoint, **kwargs)

    @property
    def url(self):
        kwargs = {'offset': self.offset}
        if self.limit > 0:
            kwargs['limit'] = self.limit
        return url_for(request.endpoint, **kwargs)

    def __iter__(self):
        for item in self.items:
            result = OrderedDict()
            for key in item.keys():
                result[key] = getattr(item, key)
            yield result
