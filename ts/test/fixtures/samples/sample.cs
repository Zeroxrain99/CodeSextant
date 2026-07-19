using System;

namespace Demo
{
    public delegate void Handler();

    public interface IShape
    {
        double Area();
    }

    public enum Color { Red, Green }

    public struct Point
    {
        public int X;
    }

    public record Person(string Name);

    public class Service
    {
        public Service() {}

        public int Value { get; set; }

        public void Run() {}
    }
}
