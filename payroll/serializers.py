from rest_framework import serializers

from payroll.models import PayrollEntry, PayrollPayment, PayrollRun


class PayrollRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollRun
        fields = "__all__"


class PayrollEntrySerializer(serializers.ModelSerializer):
    gross_pay = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    net_pay = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = PayrollEntry
        fields = "__all__"


class PayrollPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollPayment
        fields = "__all__"
