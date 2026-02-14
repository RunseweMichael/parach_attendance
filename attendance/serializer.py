from rest_framework import serializers
from django.contrib.auth import authenticate, get_user_model, login, logout

User= get_user_model()

class SignupSerializer(serializers.Serializer):
    first_name= serializers.CharField(max_length=12)
    last_name= serializers.CharField(max_length=12)
    username= serializers.CharField(max_length=20)
    email= serializers.EmailField()
    password= serializers.CharField(max_length=6, write_only=True)
    user_type= serializers.ChoiceField(
        choices=User.USER_TYPE_CHOICES, default="student"
    )
    
    def username(self, value):

        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already Exists")
        return value
    def create(self, validated_data):
        password= validated_data.pop("password")
        user= User.objects.create_user(
            **validated_data
        )
        user.set_password(password)
        user.save()
        return user
    
class LoginSerializer(serializers.Serializer):
    username= serializers.CharField(required=True)
    password= serializers.CharField(write_only=True, required=True)

    def validate(self, attrs):
        username_input= attrs.get("username")
        password= attrs.get("password")

        if username_input and "@" in username_input:
            user=User.objects.filter(email__iexact= username_input).first()
            if user:
                username_input= user.username
        user= authenticate(
            username=username_input,
            password= password
        )
        if not user:
            raise serializers.ValidationError("Invalid Credentials")
        
        attrs["user"]= user

        return attrs
    

        



 




