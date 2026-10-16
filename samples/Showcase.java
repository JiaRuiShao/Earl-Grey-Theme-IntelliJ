package com.earlgrey.demo;

import java.io.IOException;
import java.io.StringReader;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.Supplier;

import static java.lang.Math.PI;
import static java.lang.Math.max;
import static com.earlgrey.demo.Showcase.hits;

/**
 * Showcase of every Java symbol kind, for theme comparison.
 * <p>
 * See {@link Shape#area()} and {@code Showcase.GREETING}.
 *
 * @param <T> the element type
 * @author Earl Grey
 * @see Planet
 * @since 1.0
 */
@Marker(value = "showcase", priority = 2)
public class Showcase<T extends Comparable<T>> implements Supplier<List<T>> {

    // ----- fields -----
    static int hits = 0;                                   // static field
    static final String GREETING = "Hello, \"tea\"\n";     // static final field (constant)
    public static final int MAX_SIZE = 0x7F_FF;            // public constant
    private final List<T> items = new ArrayList<>();       // instance final field
    private int size;                                      // instance field
    protected volatile boolean running = true;             // protected instance field
    transient long timestamp = 1_000L;                     // package-private instance field

    static {
        hits = MAX_SIZE >>> 4;
    }

    {
        size = 017;
    }

    /**
     * Constructor declaration.
     *
     * @param initialSize the starting size
     */
    public Showcase(int initialSize) {
        this.size = initialSize;
        hits++;
    }

    // ----- methods -----
    @Override
    public List<T> get() {
        return items;
    }

    public void add(T item) {
        items.add(item);
        size += 1;
    }

    public <R> List<R> transform(Function<? super T, ? extends R> mapper) {
        List<R> result = new ArrayList<>(size);
        for (T item : items) {
            result.add(mapper.apply(item));
        }
        return result;
    }

    static int sum(int... values) {
        int total = 0;
        for (int v : values) {
            total += v;
        }
        return max(total, Collections.<Integer>emptyList().size());
    }

    @SuppressWarnings("unchecked")
    String describe(Object input, int depth) {
        depth = depth + 1;                                 // reassigned parameter
        String label = "depth=" + depth;
        if (input instanceof String text && !text.isEmpty()) {
            label += ':' + text;                           // reassigned local
        }
        if (input instanceof List<?> raw) {
            List<String> names = (List<String>) raw;       // unchecked cast
            label += names.size();
        }
        String kind = switch (input) {
            case Integer i when i > 0 -> "positive";
            case Point(int x, int y) -> "point " + (x + y);
            case null -> "nothing";
            default -> {
                char c = '\t';
                yield "other" + c + '\u00e9';
            }
        };
        return label + kind;
    }

    double circle(double radius) {
        final double area = PI * radius * radius;
        var builder = new StringBuilder();
        builder.append(area).append(GREETING);
        Runnable task = new Runnable() {
            @Override
            public void run() {
                System.out.println(builder);
            }
        };
        task.run();
        Function<Integer, Integer> square = n -> n * n;
        BiFunction<String, Integer, String> repeat = (String s, Integer times) -> s.repeat(times) + area;
        Supplier<List<String>> factory = ArrayList::new;
        Optional<String> maybe = Optional.of("earl").map(String::toUpperCase);
        String json = """
                {"tea": "earl grey", "hot": true}
                """;
        outer:
        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 3; j++) {
                if (i * j > 2 || i == j && !running) break outer;
            }
        }
        // TODO: steep for three minutes
        return area + square.apply(2) + factory.get().size() + maybe.orElse("").length() + repeat.apply(json, 1).length();
    }

    long legacy() throws InterruptedException {
        Thread current = Thread.currentThread();
        Thread.sleep(0);
        return current.getId();
    }

    String read(String text) throws IOException {
        try (StringReader reader = new StringReader(text)) {
            return reader.read() == -1 ? "" : text;
        }
    }

    void sync(Map.Entry<String, Integer> entry) {
        synchronized (this) {
            try {
                int[][] grid = new int[2][2];
                grid[0][1] = entry.getValue();
                assert grid.length == 2 : "bad grid";
            } catch (IllegalStateException | ArithmeticException e) {
                throw new RuntimeException(e.getMessage(), e);
            } finally {
                running = false;
            }
        }
        class LocalHelper {
            int twice(int n) { return n << 1; }
        }
        size = new LocalHelper().twice(size);
        Class<?> type = String.class;
        System.out.printf("%s %d %.2f %b%n", type.getSimpleName(), 0b1010, 1.5e3f, null == entry);
    }

    private native void nativeHook();

    // ----- nested types -----
    static class Builder {
        private String name = "";

        Builder name(String name) {
            this.name = name;
            return this;
        }

        Showcase<String> build() {
            Showcase<String> showcase = new Showcase<>(name.length());
            showcase.add(name);
            return showcase;
        }
    }

    class Inner {
        int peek() {
            return size + items.size();
        }
    }
}

// ----- annotation type -----
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Marker {
    String value() default "earl-grey";

    int priority() default 1;
}

// ----- interfaces -----
@FunctionalInterface
interface Shape {
    int VERSION = 1;                                       // interface constant

    double area();

    default String label() {
        return "Shape(" + area() + ") v" + VERSION;
    }

    static Shape unit() {
        return () -> 1.0;
    }
}

sealed interface Expr permits Num, Add {
}

// ----- records -----
record Num(int value) implements Expr {
}

record Add(Expr left, Expr right) implements Expr {
    int eval() {
        return left instanceof Num(int a) && right instanceof Num(int b) ? a + b : 0;
    }
}

record Point(int x, int y) {
    static final Point ORIGIN = new Point(0, 0);

    Point {
        if (x < 0) throw new IllegalArgumentException("x < 0");
    }

    double distance() {
        return Math.sqrt(x * x + y * y);
    }
}

// ----- enum -----
enum Planet {
    MERCURY(3.303e+23),
    EARTH(5.976e+24) {
        @Override
        String nickname() {
            return "Blue";
        }
    };

    private final double mass;

    Planet(double mass) {
        this.mass = mass;
    }

    String nickname() {
        return name().toLowerCase() + mass;
    }
}

// ----- class hierarchy -----
sealed abstract class Animal permits Dog, Cat {
    protected String name;

    abstract String sound();

    void speak() {
        System.out.println(name + " says " + sound());
    }
}

final class Dog extends Animal {
    Dog(String name) {
        this.name = name;
    }

    @Override
    String sound() {
        return "woof";
    }

    void greet(Animal other) throws TeaException {
        speak();
        super.speak();
        other.speak();
        if (other instanceof Cat) throw new TeaException("hiss");
        System.out.println(hits + Showcase.sum(1, 2, 3) + Planet.EARTH.nickname() + Point.ORIGIN.x());
    }
}

non-sealed class Cat extends Animal {
    @Override
    String sound() {
        return "meow";
    }
}

class TeaException extends Exception {
    TeaException(String message) {
        super(message);
    }
}
