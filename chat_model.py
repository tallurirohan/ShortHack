# chat_model.py

import pandas as pd
import pickle
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors


class ExcelChatModel:
    def __init__(self, df):
        self.df = df.fillna("")
        self.vectorizer = TfidfVectorizer(stop_words='english')
        self.nn = NearestNeighbors(n_neighbors=1, metric='cosine')
        self.texts = self._build_corpus(self.df)
        self.vectors = self.vectorizer.fit_transform(self.texts)
        self.nn.fit(self.vectors)

    def _build_corpus(self, df):
        return [' | '.join(str(cell) for cell in row if str(cell).strip()) for _, row in df.iterrows()]

    def query(self, prompt):
        vector = self.vectorizer.transform([prompt])
        distance, index = self.nn.kneighbors(vector)

        if distance[0][0] > 0.7:
            return "❌ I couldn't find anything relevant. Try rephrasing or provide more details."

        row_index = index[0][0]
        matched_row = self.df.iloc[row_index]
        response_lines = []
        for col, val in matched_row.items():
            if str(val).strip():
                response_lines.append(f"**{col}**: {val}")
        return "\n".join(response_lines)

    def save(self, path):
        with open(path, 'wb') as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path):
        with open(path, 'rb') as f:
            return pickle.load(f)
