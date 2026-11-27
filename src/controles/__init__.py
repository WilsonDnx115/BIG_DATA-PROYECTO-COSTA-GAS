"""Controles preventivos y validacion de identidad (W16, W17).

De este paquete W22 usa `jwt.py`, que valida el token de Cognito. El control
previo al pago (`control_pago.py`) llega con W16, cuando este `fact_alerta`
(W12): sin esa tabla el semaforo del pago no tiene con que responder.
"""
