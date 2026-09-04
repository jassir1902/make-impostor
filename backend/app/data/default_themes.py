"""
Catálogo de temáticas oficiales "quemadas" en código para la Fase 1
(ver 04_roadmap_and_phases.md). En Fase 4 esto se migra a Supabase/Postgres
sin cambiar la forma del modelo Topic, que ya está diseñado para
serializar directamente (ver 01_game_design.md, sección 8 y 04, Fase 4).
"""

from app.models.game import Topic, Word


def load_default_topics() -> list[Topic]:
    return [
        Topic(
            name="Animales",
            is_official=True,
            words=[
                Word(name="Perro", hint="Mamífero doméstico, mueve la cola"),
                Word(name="Gato", hint="Mamífero doméstico, maúlla"),
                Word(name="Elefante", hint="El terrestre más grande"),
                Word(name="León", hint="El rey de la selva"),
                Word(name="Delfín", hint="Mamífero marino muy inteligente"),
                Word(name="Águila", hint="Ave rapaz de vista aguda"),
                Word(name="Serpiente", hint="Reptil sin patas"),
                Word(name="Pingüino", hint="Ave que no vuela, vive en el frío"),
            ],
        ),
        Topic(
            name="Comida",
            is_official=True,
            words=[
                Word(name="Pizza", hint="Plato italiano con queso derretido"),
                Word(name="Sushi", hint="Plato japonés con arroz y pescado crudo"),
                Word(name="Tacos", hint="Plato mexicano en tortilla"),
                Word(name="Hamburguesa", hint="Pan con carne, típico de comida rápida"),
                Word(name="Ceviche", hint="Plato con pescado o marisco crudo en cítrico"),
                Word(name="Empanada", hint="Masa rellena, horneada o frita"),
                Word(name="Helado", hint="Postre frío"),
                Word(name="Sopa", hint="Plato líquido y caliente"),
            ],
        ),
        Topic(
            name="Profesiones",
            is_official=True,
            words=[
                Word(name="Médico", hint="Atiende pacientes en un hospital"),
                Word(name="Bombero", hint="Apaga incendios"),
                Word(name="Maestro", hint="Enseña en un salón de clases"),
                Word(name="Piloto", hint="Conduce aviones"),
                Word(name="Chef", hint="Cocina en un restaurante"),
                Word(name="Policía", hint="Hace cumplir la ley"),
                Word(name="Ingeniero", hint="Diseña y construye sistemas"),
                Word(name="Abogado", hint="Representa casos legales"),
            ],
        ),
        Topic(
            name="Lugares Famosos",
            is_official=True,
            words=[
                Word(name="Torre Eiffel", hint="Monumento de hierro en Francia"),
                Word(name="Machu Picchu", hint="Ciudadela inca en Perú"),
                Word(name="Gran Muralla China", hint="Muro de miles de kilómetros"),
                Word(name="Coliseo Romano", hint="Anfiteatro antiguo en Italia"),
                Word(name="Estatua de la Libertad", hint="Monumento en Nueva York"),
                Word(name="Pirámides de Guiza", hint="Antiguas tumbas egipcias"),
                Word(name="Taj Mahal", hint="Mausoleo de mármol en India"),
            ],
        ),
    ]
