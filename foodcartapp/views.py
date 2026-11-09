from django.db import transaction
from django.http import JsonResponse
from django.templatetags.static import static
from phonenumber_field.serializerfields import PhoneNumberField
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers
from .models import Product, Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    product = serializers.IntegerField()

    class Meta:
        model = OrderItem
        fields = ['product', 'quantity']


class OrderSerializer(serializers.ModelSerializer):
    phonenumber = PhoneNumberField()
    products = OrderItemSerializer(
        many=True,
        allow_empty=False,
        write_only=True,
    )

    class Meta:
        model = Order
        fields = [
            'id',
            'firstname',
            'lastname',
            'phonenumber',
            'address',
            'products',
        ]
        extra_kwargs = {
            'firstname': {'allow_blank': False, 'required': True},
            'lastname': {'allow_blank': False, 'required': True},
            'address': {'allow_blank': False, 'required': True},
        }

    def validate_products(self, value):
        product_ids = [item['product'] for item in value]
        products = Product.objects.filter(id__in=product_ids).only('id', 'price')
        products_by_id = {product.id: product for product in products}

        missing_ids = set(product_ids) - set(products_by_id.keys())
        if missing_ids:
            raise serializers.ValidationError(
                f'ID {list(missing_ids)} не найдены.'
            )

        for item in value:
            item['product'] = products_by_id[item['product']]

        return value

    def create(self, validated_data):
        products_data = validated_data.pop('products')
        with transaction.atomic():
            order = Order.objects.create(**validated_data)
            order_items = [
                OrderItem(
                    order=order,
                    product=item['product'],
                    quantity=item['quantity'],
                    price=item['product'].price,
                )
                for item in products_data
            ]
            OrderItem.objects.bulk_create(order_items)

        return order


def banners_list_api(request):
    # FIXME move data to db?
    return JsonResponse([
        {
            'title': 'Burger',
            'src': static('burger.jpg'),
            'text': 'Tasty Burger at your door step',
        },
        {
            'title': 'Spices',
            'src': static('food.jpg'),
            'text': 'All Cuisines',
        },
        {
            'title': 'New York',
            'src': static('tasty.jpg'),
            'text': 'Food is incomplete without a tasty dessert',
        }
    ], safe=False, json_dumps_params={
        'ensure_ascii': False,
        'indent': 4,
    })


def product_list_api(request):
    products = Product.objects.select_related('category').available()

    dumped_products = []
    for product in products:
        dumped_product = {
            'id': product.id,
            'name': product.name,
            'price': product.price,
            'special_status': product.special_status,
            'description': product.description,
            'category': {
                'id': product.category.id,
                'name': product.category.name,
            } if product.category else None,
            'image': product.image.url,
            'restaurant': {
                'id': product.id,
                'name': product.name,
            }
        }
        dumped_products.append(dumped_product)
    return JsonResponse(dumped_products, safe=False, json_dumps_params={
        'ensure_ascii': False,
        'indent': 4,
    })


class RegisterOrderAPIView(APIView):
    def post(self, request):
        serializer = OrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class TestAPIView(APIView):
    def get(self, request):
        return Response({'status': 'DRF works!'})
