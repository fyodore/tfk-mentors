from django.test import TestCase

from tasks import views  # noqa: F401  (import covers the placeholder module)


class TasksViewsImportTests(TestCase):
    def test_views_module_imports(self):
        self.assertTrue(hasattr(views, "render"))
