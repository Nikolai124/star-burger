from django.db import models
from django.db.models import F, Sum
from django.core.validators import MinValueValidator
from phonenumber_field.modelfields import PhoneNumberField

from .geocoding import get_coordinates


class Restaurant(models.Model):
    name = models.CharField(
        'название',
        max_length=50
    )
    address = models.CharField(
        'адрес',
        max_length=100,
        blank=True,
    )
    contact_phone = models.CharField(
        'контактный телефон',
        max_length=50,
        blank=True,
    )
    lat = models.FloatField('широта', null=True, blank=True)
    lon = models.FloatField('долгота', null=True, blank=True)

    class Meta:
        verbose_name = 'ресторан'
        verbose_name_plural = 'рестораны'

    def __str__(self):
        return self.name

    @property
    def coordinates(self):
        if self.lat is None or self.lon is None:
            return None
        return self.lon, self.lat

    def save(self, *args, **kwargs):
        if self.address and not self.coordinates:
            coords = get_coordinates(self.address)
            if coords:
                self.lon, self.lat = coords
        super().save(*args, **kwargs)


class ProductQuerySet(models.QuerySet):
    def available(self):
        products = (
            RestaurantMenuItem.objects
            .filter(availability=True)
            .values_list('product')
        )
        return self.filter(pk__in=products)


class ProductCategory(models.Model):
    name = models.CharField(
        'название',
        max_length=50
    )

    class Meta:
        verbose_name = 'категория'
        verbose_name_plural = 'категории'

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(
        'название',
        max_length=50
    )
    category = models.ForeignKey(
        ProductCategory,
        verbose_name='категория',
        related_name='products',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    price = models.DecimalField(
        'цена',
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    image = models.ImageField(
        'картинка'
    )
    special_status = models.BooleanField(
        'спец.предложение',
        default=False,
        db_index=True,
    )
    description = models.TextField(
        'описание',
        max_length=200,
        blank=True,
    )

    objects = ProductQuerySet.as_manager()

    class Meta:
        verbose_name = 'товар'
        verbose_name_plural = 'товары'

    def __str__(self):
        return self.name


class RestaurantMenuItem(models.Model):
    restaurant = models.ForeignKey(
        Restaurant,
        related_name='menu_items',
        verbose_name="ресторан",
        on_delete=models.CASCADE,
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='menu_items',
        verbose_name='продукт',
    )
    availability = models.BooleanField(
        'в продаже',
        default=True,
        db_index=True
    )

    class Meta:
        verbose_name = 'пункт меню ресторана'
        verbose_name_plural = 'пункты меню ресторана'
        unique_together = [
            ['restaurant', 'product']
        ]

    def __str__(self):
        return f"{self.restaurant.name} - {self.product.name}"


class OrderQuerySet(models.QuerySet):
    def with_total_cost(self):
        return self.annotate(
            total_cost=Sum(F('items__price') * F('items__quantity'))
        )


class Order(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'Новый'
        COOKING = 'cooking', 'Готовится'
        DELIVERING = 'delivering', 'Доставляется'
        DONE = 'done', 'Выполнен'

    class PaymentMethod(models.TextChoices):
        CASH = 'cash', 'Наличными курьеру'
        ELECTRONIC = 'electronic', 'Электронно'

    firstname = models.CharField(
        'имя',
        max_length=50,
    )
    lastname = models.CharField(
        'фамилия',
        max_length=50,
    )
    phonenumber = PhoneNumberField(
        'номер телефона',
    )
    address = models.CharField(
        'адрес',
        max_length=200,
    )
    status = models.CharField(
        'статус',
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True,
    )
    payment_method = models.CharField(
        'способ оплаты',
        max_length=20,
        choices=PaymentMethod.choices,
        blank=True,
    )
    comment = models.TextField(
        'комментарий менеджера',
        blank=True,
    )
    created_at = models.DateTimeField(
        'создан',
        auto_now_add=True,
        db_index=True,
    )
    updated_at = models.DateTimeField(
        'изменён',
        auto_now=True,
    )

    objects = OrderQuerySet.as_manager()

    class Meta:
        verbose_name = 'заказ'
        verbose_name_plural = 'заказы'

    def __str__(self):
        return f"{self.firstname} {self.lastname}, {self.address}"

    def get_available_restaurants(self):
        restaurants_for_items = [
            {
                menu_item.restaurant
                for menu_item in item.product.menu_items.all()
                if menu_item.availability
            }
            for item in self.items.all()
        ]
        if not restaurants_for_items:
            return set()
        return set.intersection(*restaurants_for_items)


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        related_name='items',
        verbose_name='заказ',
        on_delete=models.CASCADE,
    )
    product = models.ForeignKey(
        Product,
        related_name='order_items',
        verbose_name='товар',
        on_delete=models.PROTECT,
    )
    quantity = models.PositiveIntegerField(
        'количество',
        validators=[MinValueValidator(1)],
    )
    price = models.DecimalField(
        'цена',
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        verbose_name = 'элемент заказа'
        verbose_name_plural = 'элементы заказа'

    def __str__(self):
        return f"{self.product.name} - {self.order}"


class Geocache(models.Model):
    address = models.CharField(
        'адрес',
        max_length=255,
        unique=True,
        db_index=True,
    )
    lat = models.FloatField('широта', null=True, blank=True)
    lon = models.FloatField('долгота', null=True, blank=True)
    updated_at = models.DateTimeField(
        'дата обновления',
        auto_now=True,
    )

    class Meta:
        verbose_name = 'кэш геокодирования'

    def __str__(self):
        return self.address
