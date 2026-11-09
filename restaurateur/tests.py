from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from foodcartapp.models import Order, OrderItem, Product, Restaurant, RestaurantMenuItem
from foodcartapp.tests import mock_geocoder

# Create your tests here.


class ManagerOrdersTests(TestCase):
    def setUp(self):
        mock_geocoder(self)
        manager = get_user_model().objects.create_user('manager', password='password', is_staff=True)
        self.client.force_login(manager)

        self.burger = Product.objects.create(name='Чизбургер', price=199, image='burger.png')
        self.fries = Product.objects.create(name='Картофель фри', price=99, image='fries.png')
        self.cola = Product.objects.create(name='Кола', price=79, image='cola.png')
        self.ice_cream = Product.objects.create(name='Мороженое', price=59, image='ice_cream.png')

        tverskaya = Restaurant.objects.create(name='Star Burger Тверская', address='Москва, Тверская улица, 1')
        arbat = Restaurant.objects.create(name='Star Burger Арбат', address='Москва, Арбат, 1')
        outskirts = Restaurant.objects.create(name='Star Burger Окраина', address='Москва, улица Которой Нет, 1')
        RestaurantMenuItem.objects.bulk_create([
            RestaurantMenuItem(restaurant=tverskaya, product=self.burger),
            RestaurantMenuItem(restaurant=tverskaya, product=self.fries),
            RestaurantMenuItem(restaurant=arbat, product=self.burger),
            RestaurantMenuItem(restaurant=arbat, product=self.fries, availability=False),
            RestaurantMenuItem(restaurant=outskirts, product=self.burger),
            RestaurantMenuItem(restaurant=outskirts, product=self.cola),
        ])

    def create_order(self, products, address='Москва, Красная площадь, 1'):
        order = Order.objects.create(
            firstname='Иван',
            lastname='Петров',
            phonenumber='+79291234567',
            address=address,
        )
        OrderItem.objects.bulk_create([
            OrderItem(order=order, product=product, quantity=1, price=product.price)
            for product in products
        ])
        return order

    def get_orders_page(self):
        response = self.client.get(reverse('restaurateur:view_orders'))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def get_order_row(self, order):
        page = self.get_orders_page()
        row_start = page.index(f'>#{order.id}</a>')
        return page[row_start:page.index('</tr>', row_start)]

    def test_empty_list(self):
        self.assertIn('Заказов пока нет', self.get_orders_page())

    def test_list_shows_orders(self):
        orders = [
            self.create_order([self.burger]),
            self.create_order([self.burger, self.fries]),
            self.create_order([self.ice_cream]),
        ]

        page = self.get_orders_page()

        self.assertNotIn('Заказов пока нет', page)
        for order in orders:
            self.assertIn(f'>#{order.id}</a>', page)
        self.assertIn('298 руб.', page)

    def test_query_count_does_not_depend_on_orders_count(self):
        for _ in range(3):
            self.create_order([self.burger, self.fries])
        self.get_orders_page()
        with CaptureQueriesContext(connection) as few_orders:
            self.get_orders_page()

        for _ in range(30):
            self.create_order([self.burger, self.fries])
        with CaptureQueriesContext(connection) as many_orders:
            self.get_orders_page()

        self.assertEqual(len(many_orders), len(few_orders))

    def test_order_edit_is_saved_and_shown(self):
        order = self.create_order([self.burger])
        item = order.items.get()

        response = self.client.post(
            reverse('restaurateur:edit_order', args=[order.id]),
            {
                'status': Order.Status.COOKING,
                'payment_method': Order.PaymentMethod.ELECTRONIC,
                'comment': 'Позвонить за час',
                'firstname': 'Иван',
                'lastname': 'Петров',
                'phonenumber': '+79291234567',
                'address': 'Москва, Арбат, 1',
                'items-TOTAL_FORMS': 1,
                'items-INITIAL_FORMS': 1,
                'items-MIN_NUM_FORMS': 0,
                'items-MAX_NUM_FORMS': 1000,
                'items-0-id': item.id,
                'items-0-quantity': 3,
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('restaurateur:view_order', args=[order.id]))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COOKING)
        self.assertEqual(order.payment_method, Order.PaymentMethod.ELECTRONIC)
        self.assertEqual(order.comment, 'Позвонить за час')
        self.assertEqual(order.address, 'Москва, Арбат, 1')
        self.assertEqual(order.items.get().quantity, 3)

        detail_page = response.content.decode()
        self.assertIn('Готовится', detail_page)
        self.assertIn('Электронно', detail_page)
        self.assertIn('Москва, Арбат, 1', detail_page)
        self.assertIn('597 руб.', detail_page)

        edit_page = self.client.get(reverse('restaurateur:edit_order', args=[order.id])).content.decode()
        self.assertIn('Позвонить за час', edit_page)

        row = self.get_order_row(order)
        self.assertIn('Москва, Арбат, 1', row)
        self.assertIn('Электронно', row)

    def test_done_order_is_hidden_from_list(self):
        order = self.create_order([self.burger])
        order.status = Order.Status.DONE
        order.save()

        self.assertNotIn(f'>#{order.id}</a>', self.get_orders_page())

    def test_restaurants_depend_on_order_products(self):
        burger_order = self.create_order([self.burger])
        burger_and_fries_order = self.create_order([self.burger, self.fries])
        burger_and_cola_order = self.create_order([self.burger, self.cola])

        burger_row = self.get_order_row(burger_order)
        for name in ['Star Burger Тверская', 'Star Burger Арбат', 'Star Burger Окраина']:
            self.assertIn(name, burger_row)

        burger_and_fries_row = self.get_order_row(burger_and_fries_order)
        self.assertIn('Star Burger Тверская', burger_and_fries_row)
        self.assertNotIn('Star Burger Арбат', burger_and_fries_row)
        self.assertNotIn('Star Burger Окраина', burger_and_fries_row)

        burger_and_cola_row = self.get_order_row(burger_and_cola_order)
        self.assertIn('Star Burger Окраина', burger_and_cola_row)
        self.assertNotIn('Star Burger Тверская', burger_and_cola_row)
        self.assertNotIn('Star Burger Арбат', burger_and_cola_row)

    def test_nearest_restaurant_goes_first(self):
        order = self.create_order([self.burger])

        row = self.get_order_row(order)

        self.assertIn('<strong>Star Burger Тверская</strong>', row)
        self.assertIn('(0,19 км)', row)
        self.assertIn('(1,27 км)', row)
        self.assertIn('(расстояние неизвестно)', row)
        self.assertLess(row.index('Star Burger Тверская'), row.index('Star Burger Арбат'))
        self.assertLess(row.index('Star Burger Арбат'), row.index('Star Burger Окраина'))

    def test_order_without_suitable_restaurants(self):
        order = self.create_order([self.burger, self.ice_cream])

        self.assertIn('Нет подходящих ресторанов', self.get_order_row(order))

    def test_order_with_unknown_address(self):
        order = self.create_order([self.burger], address='Москва, улица Которой Нет, 5')

        row = self.get_order_row(order)

        self.assertIn('Не удалось определить координаты адреса', row)
        self.assertNotIn('<strong>', row)
        self.assertEqual(row.count('(расстояние неизвестно)'), 3)

    def test_order_with_single_product(self):
        order = self.create_order([self.fries])

        row = self.get_order_row(order)

        self.assertIn('99 руб.', row)
        self.assertIn('Посмотреть товары (1)', row)
        self.assertIn('Картофель фри × 1', row)
        self.assertIn('<strong>Star Burger Тверская</strong>', row)
