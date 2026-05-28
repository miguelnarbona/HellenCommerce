import Levenshtein

class BKTree:
    def __init__(self, palabra):
        self.palabra = palabra
        self.hijos = {}  # distancia → nodo

    def insertar(self, nueva):
        d = Levenshtein.distance(nueva, self.palabra)

        if d in self.hijos:
            self.hijos[d].insertar(nueva)
        else:
            self.hijos[d] = BKTree(nueva)

    def buscar(self, palabra, max_dist=2):
        resultados = []
        d = Levenshtein.distance(palabra, self.palabra)

        if d <= max_dist:
            resultados.append((d, self.palabra))

        for dist_hijo, nodo in self.hijos.items():
            if d - max_dist <= dist_hijo <= d + max_dist:
                resultados.extend(nodo.buscar(palabra, max_dist))

        return resultados
