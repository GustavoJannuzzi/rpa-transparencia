"""Os três tipos de problema que o núcleo trata de jeitos diferentes."""


class FalhaTransitoria(Exception):
    """Portal fora do ar, lento ou devolvendo 5xx: vale tentar de novo com espera."""


class PortalMudou(Exception):
    """Seletor sumiu, coluna mudou, resposta com outro formato.

    A fonte para e avisa, em vez de gravar lixo. Não adianta repetir.
    """


class BloqueadoPorRobots(Exception):
    """O robots.txt do portal não permite o caminho. A coleta não entra."""


class AcessoRecusado(Exception):
    """Captcha, login ou bloqueio explícito. Nunca se contorna: a fonte fica de fora."""
