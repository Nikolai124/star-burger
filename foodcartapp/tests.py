from decimal import Decimal
from unittest import mock

from django.test import TestCase

from .geocoding import calculate_distance, get_coordinates
from .models import Geocache, Order, Product, Restaurant


PLACES = {
    'Москва, Тверская улица, 1': '37.614716 55.756315',
    'Москва, Арбат, 1': '37.598334 55.752068',
    'Москва, Красная площадь, 1': '37.6176 55.7558',
}


def fake_geocoder(url, params, timeout):
    position = PLACES.get(params['geocode'])
    found_places = [{'GeoObject': {'Point': {'pos': position}}}] if position else []
    response = mock.Mock()
    response.json.return_value = {
        'response': {'GeoObjectCollection': {'featureMember': found_places}},
    }
    return response


def mock_geocoder(test_case):
    patcher = mock.patch('foodcartapp.geocoding.requests.get', side_effect=fake_geocoder)
    test_case.addCleanup(patcher.stop)
    return patcher.start()


class RegisterOrderAPITests(TestCase):
    url = '/api/order/'

    def setUp(self):
        mock_geocoder(self)
        self.burger = Product.objects.create(name='Чизбургер', price=199, image='burger.png')
        self.fries = Product.objects.create(name='Картофель фри', price=99, image='fries.png')

    def make_payload(self):
        return {
            'products': [
                {'product': self.burger.id, 'quantity': 2},
                {'product': self.fries.id, 'quantity': 1},
            ],
            'firstname': 'Иван',
            'lastname': 'Петров',
            'phonenumber': '+79291234567',
            'address': 'Москва, Красная площадь, 1',
        }

    def post_order(self, payload):
        return self.client.post(self.url, payload, content_type='application/json')

    def test_order_is_saved_to_database(self):
        response = self.post_order(self.make_payload())

        self.assertEqual(response.status_code, 201)
        order = Order.objects.with_total_cost().get()
        self.assertEqual(response.json()['id'], order.id)
        self.assertEqual(order.firstname, 'Иван')
        self.assertEqual(order.lastname, 'Петров')
        self.assertEqual(str(order.phonenumber), '+79291234567')
        self.assertEqual(order.address, 'Москва, Красная площадь, 1')
        self.assertEqual(order.status, Order.Status.NEW)
        self.assertEqual(
            list(order.items.order_by('id').values_list('product__name', 'quantity', 'price')),
            [('Чизбургер', 2, Decimal('199')), ('Картофель фри', 1, Decimal('99'))],
        )
        self.assertEqual(order.total_cost, Decimal('497'))

    def test_item_price_does_not_change_with_product_price(self):
        self.post_order(self.make_payload())

        self.burger.price = 250
        self.burger.save()

        self.assertEqual(Order.objects.with_total_cost().get().total_cost, Decimal('497'))

    def test_order_without_required_field_is_rejected(self):
        for field in ['products', 'firstname', 'lastname', 'phonenumber', 'address']:
            with self.subTest(field=field):
                payload = self.make_payload()
                del payload[field]

                response = self.post_order(payload)

                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json())
        self.assertFalse(Order.objects.exists())

    def test_order_with_wrong_value_is_rejected(self):
        wrong_values = [
            ('products', None),
            ('products', []),
            ('products', 'Чизбургер'),
            ('products', [{'product': 9999, 'quantity': 1}]),
            ('products', [{'product': self.burger.id, 'quantity': 0}]),
            ('firstname', None),
            ('firstname', ''),
            ('lastname', ''),
            ('phonenumber', ''),
            ('phonenumber', '+70000000000'),
            ('address', ''),
        ]
        for field, value in wrong_values:
            with self.subTest(field=field, value=value):
                payload = self.make_payload()
                payload[field] = value

                response = self.post_order(payload)

                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json())
        self.assertFalse(Order.objects.exists())


class GeocodingTests(TestCase):
    def setUp(self):
        self.geocoder = mock_geocoder(self)

    def test_address_is_requested_only_once(self):
        first = get_coordinates('Москва, Арбат, 1')
        second = get_coordinates('Москва, Арбат, 1')

        self.assertEqual(first, (37.598334, 55.752068))
        self.assertEqual(second, first)
        self.assertEqual(self.geocoder.call_count, 1)
        self.assertEqual(Geocache.objects.count(), 1)

    def test_unknown_address_is_cached_too(self):
        self.assertIsNone(get_coordinates('Москва, улица Которой Нет, 1'))
        self.assertIsNone(get_coordinates('Москва, улица Которой Нет, 1'))

        self.assertEqual(self.geocoder.call_count, 1)

    def test_restaurant_gets_coordinates_on_save(self):
        restaurant = Restaurant.objects.create(name='Star Burger Арбат', address='Москва, Арбат, 1')

        restaurant.refresh_from_db()
        self.assertEqual(restaurant.coordinates, (37.598334, 55.752068))

    def test_distance_between_known_points(self):
        tverskaya = (37.614716, 55.756315)
        arbat = (37.598334, 55.752068)

        self.assertEqual(calculate_distance(tverskaya, arbat), 1.13)
        self.assertEqual(calculate_distance(arbat, tverskaya), 1.13)
        self.assertEqual(calculate_distance(arbat, arbat), 0)
