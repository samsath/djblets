

from contextlib import contextmanager

from django.contrib.sites.models import Site

from djblets.testing.testcases import TestCase
from djblets.webapi.resources.base import WebAPIResource
from djblets.webapi.resources.registry import (get_resource_for_object,
                                               register_resource_for_model,
                                               unregister_resource_for_model)


@contextmanager
def register_resource_for_model_temp(model, resource):
    """A context manager to temporarily register a resource for a model."""
    register_resource_for_model(model, resource)

    try:
        yield
    finally:
        unregister_resource_for_model(model)


class ResourceRegistryTests(TestCase):
    """Tests for the resource registry."""

    def test_get_resource_for_object_only_fields(self):
        """Testing get_resource_for_model when model is deferred"""
        class TestResource(WebAPIResource):
            pass

        resource = TestResource()

        with register_resource_for_model_temp(Site, resource):
            config = Site.objects.only('domain').get()

            self.assertEqual(get_resource_for_object(config),
                             resource)
