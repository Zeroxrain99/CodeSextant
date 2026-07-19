pub fn free_fn() {}

pub struct MyStruct {
    field: i32,
}

pub enum MyEnum {
    A,
    B,
}

pub trait MyTrait {
    fn required(&self);
}

impl MyStruct {
    pub fn method(&self) {}
}

const MAX: i32 = 100;
static NAME: &str = "x";
