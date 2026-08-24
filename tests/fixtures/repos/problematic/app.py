import pickle
import subprocess


def process(payload: bytes, expression: str) -> object:
    # Static fixture only. RepoInsight must never execute this code.
    subprocess.run(expression, shell=True)
    return eval(expression) or pickle.loads(payload)
