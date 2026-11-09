from django import forms
from django.db import transaction
from django.db.models import F, Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.urls import reverse_lazy
from django.contrib.auth.decorators import user_passes_test

from django.contrib.auth import authenticate, login
from django.contrib.auth import views as auth_views


from foodcartapp.geocoding import calculate_distance, get_addresses_coordinates
from foodcartapp.models import Order, OrderItem, Product, Restaurant, RestaurantMenuItem


class Login(forms.Form):
    username = forms.CharField(
        label='Логин', max_length=75, required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Укажите имя пользователя'
        })
    )
    password = forms.CharField(
        label='Пароль', max_length=75, required=True,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите пароль'
        })
    )


class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['status', 'payment_method', 'comment', 'firstname', 'lastname', 'phonenumber', 'address']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-control'}),
            'payment_method': forms.Select(attrs={'class': 'form-control'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'firstname': forms.TextInput(attrs={'class': 'form-control'}),
            'lastname': forms.TextInput(attrs={'class': 'form-control'}),
            'phonenumber': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


OrderItemFormSet = forms.inlineformset_factory(
    Order,
    OrderItem,
    fields=['quantity'],
    extra=0,
    can_delete=False,
    widgets={
        'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
    },
)


class LoginView(View):
    def get(self, request, *args, **kwargs):
        form = Login()
        return render(request, "login.html", context={
            'form': form
        })

    def post(self, request):
        form = Login(request.POST)

        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']

            user = authenticate(request, username=username, password=password)
            if user:
                login(request, user)
                if user.is_staff:  # FIXME replace with specific permission
                    return redirect("restaurateur:RestaurantView")
                return redirect("start_page")

        return render(request, "login.html", context={
            'form': form,
            'ivalid': True,
        })


class LogoutView(auth_views.LogoutView):
    next_page = reverse_lazy('restaurateur:login')


def is_manager(user):
    return user.is_staff  # FIXME replace with specific permission


@user_passes_test(is_manager, login_url='restaurateur:login')
def view_products(request):
    restaurants = list(Restaurant.objects.order_by('name'))
    products = list(Product.objects.prefetch_related('menu_items'))

    products_with_restaurant_availability = []
    for product in products:
        availability = {item.restaurant_id: item.availability for item in product.menu_items.all()}
        ordered_availability = [availability.get(restaurant.id, False) for restaurant in restaurants]

        products_with_restaurant_availability.append(
            (product, ordered_availability)
        )

    return render(request, template_name="products_list.html", context={
        'products_with_restaurant_availability': products_with_restaurant_availability,
        'restaurants': restaurants,
    })


@user_passes_test(is_manager, login_url='restaurateur:login')
def view_restaurants(request):
    return render(request, template_name="restaurants_list.html", context={
        'restaurants': Restaurant.objects.all(),
    })


@user_passes_test(is_manager, login_url='restaurateur:login')
def view_orders(request):
    available_menu_items = (
        RestaurantMenuItem.objects
        .filter(availability=True)
        .select_related('restaurant')
    )
    orders = (
        Order.objects
        .exclude(status=Order.Status.DONE)
        .defer('comment')
        .with_total_cost()
        .prefetch_related(
            Prefetch('items__product', queryset=Product.objects.only('name')),
            Prefetch('items__product__menu_items', queryset=available_menu_items),
        )
        .order_by('-created_at')
    )
    addresses_coordinates = get_addresses_coordinates(order.address for order in orders)
    for order in orders:
        order.coordinates = addresses_coordinates[order.address]
        order.available_restaurants = []
        for restaurant in order.get_available_restaurants():
            distance = None
            if order.coordinates and restaurant.coordinates:
                distance = calculate_distance(order.coordinates, restaurant.coordinates)
            order.available_restaurants.append((restaurant, distance))
        order.available_restaurants.sort(
            key=lambda restaurant_distance: (restaurant_distance[1] is None, restaurant_distance[1]),
        )

    return render(request, template_name='order_items.html', context={
        'order_items': orders,
    })


@user_passes_test(is_manager, login_url='restaurateur:login')
def view_order(request, order_id):
    items = (
        OrderItem.objects
        .select_related('product')
        .annotate(cost=F('price') * F('quantity'))
    )
    order = get_object_or_404(
        Order.objects
        .with_total_cost()
        .prefetch_related(Prefetch('items', queryset=items)),
        pk=order_id,
    )
    return render(request, template_name='order_detail.html', context={
        'order': order,
    })


@user_passes_test(is_manager, login_url='restaurateur:login')
def edit_order(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    items = order.items.select_related('product')

    if request.method == 'POST':
        form = OrderForm(request.POST, instance=order)
        formset = OrderItemFormSet(request.POST, instance=order, queryset=items)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
            return redirect('restaurateur:view_order', order_id=order.id)
    else:
        form = OrderForm(instance=order)
        formset = OrderItemFormSet(instance=order, queryset=items)

    return render(request, template_name='order_edit.html', context={
        'order': order,
        'form': form,
        'formset': formset,
    })
