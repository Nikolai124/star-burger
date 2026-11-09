from django.urls import path

from .views import product_list_api, banners_list_api, RegisterOrderAPIView, TestAPIView


app_name = "foodcartapp"

urlpatterns = [
    path('products/', product_list_api),
    path('banners/', banners_list_api),
    path('order/', RegisterOrderAPIView.as_view()),
    path('test/', TestAPIView.as_view()),
]
