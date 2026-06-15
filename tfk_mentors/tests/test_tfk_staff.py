from django.test import TestCase
from rest_framework.test import APIClient

from tfk_mentors.models import TfkStaff


class TfkStaffApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()

        self.alpha = TfkStaff.objects.create(
            first_name="Zara",
            last_name="Alpha",
            email="zara@example.com",
            cell_phone="555-0100",
        )
        self.beta = TfkStaff.objects.create(
            first_name="Ben",
            last_name="Beta",
            email="ben@example.com",
        )

    def test_list_sorted_by_last_name(self):
        response = self.client.get("/api/tfk-staff/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["last_name"] for row in response.data],
            ["Alpha", "Beta"],
        )

    def test_create_read_update_delete(self):
        create = self.client.post(
            "/api/tfk-staff/",
            {
                "first_name": "Chris",
                "last_name": "Gamma",
                "email": "chris@example.com",
                "cell_phone": "555-0200",
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        staff_id = create.data["id"]

        detail = self.client.get(f"/api/tfk-staff/{staff_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["first_name"], "Chris")
        self.assertEqual(detail.data["cell_phone"], "555-0200")

        update = self.client.patch(
            f"/api/tfk-staff/{staff_id}/",
            {"cell_phone": "555-0300"},
            format="json",
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.data["cell_phone"], "555-0300")

        delete = self.client.delete(f"/api/tfk-staff/{staff_id}/")
        self.assertEqual(delete.status_code, 204)
        self.assertFalse(TfkStaff.objects.filter(pk=staff_id).exists())

    def test_model_getters_and_setters(self):
        staff = TfkStaff()
        staff.set_first_name("Pat")
        staff.set_last_name("Staff")
        staff.set_email("pat@example.com")
        staff.set_cell_phone("555-0400")
        self.assertEqual(staff.get_first_name(), "Pat")
        self.assertEqual(staff.get_last_name(), "Staff")
        self.assertEqual(staff.get_email(), "pat@example.com")
        self.assertEqual(staff.get_cell_phone(), "555-0400")
