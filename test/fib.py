import sys

def generate_fibonacci(n):
    a, b, seq = 0, 1, []
    for _ in range(n):
        seq.append(a)
        a, b = b, a + b
    return seq

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python fib.py <n>")
        sys.exit(1)
    try:
        n = int(sys.argv[1])
        if n < 0:
            print("Enter a positive number.")
        else:
            print(generate_fibonacci(n))
    except ValueError:
        print("Enter a whole number.")
