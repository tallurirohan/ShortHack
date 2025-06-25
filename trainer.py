import pandas as pd
import pickle
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors


class ExcelChatModel:
    def __init__(self, df):
        self.df = df.fillna("")  # Replace NaN with empty strings
        self.vectorizer = TfidfVectorizer(stop_words='english')
        self.nn = NearestNeighbors(n_neighbors=1, metric='cosine')

        self.texts = self._build_corpus(self.df)
        self.vectors = self.vectorizer.fit_transform(self.texts)
        self.nn.fit(self.vectors)

    def _build_corpus(self, df):
        # Combine all cell values into searchable string
        return [' | '.join(str(cell) for cell in row if str(cell).strip()) for _, row in df.iterrows()]

    def query(self, prompt):
        vector = self.vectorizer.transform([prompt])
        distance, index = self.nn.kneighbors(vector)

        if distance[0][0] > 0.7:
            return "❌ I couldn't find anything relevant. Try rephrasing or provide more details."

        row_index = index[0][0]
        matched_row = self.df.iloc[row_index]

        # Build a readable summary from the row
        response_lines = []
        for col, val in matched_row.items():
            if str(val).strip():
                response_lines.append(f"**{col}**: {val}")
        return "\n".join(response_lines)

    def save(self, path):
        with open(path, 'wb') as f:
            pickle.dump(self, f)


def train_and_save_model(excel_path, model_path):
    df = pd.read_excel(excel_path)
    model = ExcelChatModel(df)
    model.save(model_path)
    print(f"✅ Model trained and saved to {model_path}")


# 👇 Run this only when training manually
if __name__ == "__main__":
    excel_file = "ai_tools.xlsx"         # <- Make sure this file exists
    model_file = "trained_model.pkl"     # <- Model will be saved here
    train_and_save_model(excel_file, model_file)
