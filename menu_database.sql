-- RAMO Restaurant Menu Database
-- Auto-generated SQL script
-- Created from menu_loader.py

BEGIN TRANSACTION;

BEGIN TRANSACTION;
CREATE TABLE allergens (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                icon TEXT
            );
INSERT INTO "allergens" VALUES(1,'орехи','🥜');
INSERT INTO "allergens" VALUES(2,'глютен','🌾');
INSERT INTO "allergens" VALUES(3,'лактоза','🥛');
INSERT INTO "allergens" VALUES(4,'яйца','🥚');
INSERT INTO "allergens" VALUES(5,'рыба','🐟');
INSERT INTO "allergens" VALUES(6,'моллюски','🦐');
INSERT INTO "allergens" VALUES(7,'соя','🫘');
INSERT INTO "allergens" VALUES(8,'кунжут','🌱');
CREATE TABLE categories (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('kitchen', 'bar')),
                sort_order INTEGER
            );
INSERT INTO "categories" VALUES(1,'Горячие блюда','kitchen',1);
INSERT INTO "categories" VALUES(2,'Горячие закуски','kitchen',2);
INSERT INTO "categories" VALUES(3,'Десерты','kitchen',3);
INSERT INTO "categories" VALUES(4,'Салаты','kitchen',4);
INSERT INTO "categories" VALUES(5,'Соусы','kitchen',5);
INSERT INTO "categories" VALUES(6,'Супы','kitchen',6);
INSERT INTO "categories" VALUES(7,'Хлеб','kitchen',7);
INSERT INTO "categories" VALUES(8,'Холодные закуски','kitchen',8);
INSERT INTO "categories" VALUES(9,'Кофе','bar',9);
INSERT INTO "categories" VALUES(10,'Лимонады','bar',10);
INSERT INTO "categories" VALUES(11,'Напитки','bar',11);
INSERT INTO "categories" VALUES(12,'Чай','bar',12);
CREATE TABLE dish_allergens (
                dish_id INTEGER NOT NULL,
                allergen_id INTEGER NOT NULL,
                PRIMARY KEY (dish_id, allergen_id),
                FOREIGN KEY (dish_id) REFERENCES dishes(id),
                FOREIGN KEY (allergen_id) REFERENCES allergens(id)
            );
INSERT INTO "dish_allergens" VALUES(4,2);
INSERT INTO "dish_allergens" VALUES(5,6);
INSERT INTO "dish_allergens" VALUES(7,6);
INSERT INTO "dish_allergens" VALUES(10,3);
INSERT INTO "dish_allergens" VALUES(12,1);
INSERT INTO "dish_allergens" VALUES(27,5);
CREATE TABLE dishes (
                id INTEGER PRIMARY KEY,
                category_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                price INTEGER,
                composition TEXT,
                description TEXT,
                is_spicy BOOLEAN DEFAULT 0,
                is_vegetarian BOOLEAN DEFAULT 0,
                is_new BOOLEAN DEFAULT 0,
                is_healthy BOOLEAN DEFAULT 0,
                FOREIGN KEY (category_id) REFERENCES categories(id)
            );
INSERT INTO "dishes" VALUES(1,6,'Рамен со свиной грудинкой',770,NULL,NULL,0,0,0,0);
INSERT INTO "dishes" VALUES(2,6,'Борщ со смальцем и печёным чесноком',590,NULL,NULL,0,0,0,0);
INSERT INTO "dishes" VALUES(3,6,'Бун рьеу с томлёными щёчками',460,NULL,NULL,1,0,0,0);
INSERT INTO "dishes" VALUES(4,6,'Домашняя куриная суп-лапша',380,NULL,NULL,0,0,0,0);
INSERT INTO "dishes" VALUES(5,6,'Суп с креветками',770,NULL,NULL,0,0,0,0);
INSERT INTO "dishes" VALUES(6,4,'Греческий с печёным перцем и копчёными оливками',550,NULL,NULL,0,0,0,0);
INSERT INTO "dishes" VALUES(7,4,'Салат с креветками и гуакамоле',690,NULL,NULL,0,0,0,0);
INSERT INTO "dishes" VALUES(8,4,'Салат с ростбифом в медово-горчичной заправке',600,NULL,NULL,0,0,0,0);
INSERT INTO "dishes" VALUES(9,4,'Тёплый салат с баклажанами',470,NULL,NULL,0,1,0,0);
INSERT INTO "dishes" VALUES(10,3,'Апероль баба с сырным кремом',450,NULL,NULL,0,1,0,0);
INSERT INTO "dishes" VALUES(11,3,'Творожные пончики',450,NULL,NULL,0,1,0,0);
INSERT INTO "dishes" VALUES(12,3,'Фисташковый тирамису',650,NULL,NULL,0,0,1,0);
INSERT INTO "dishes" VALUES(13,2,'Батат фри с трюфельным айоли',410,NULL,NULL,0,1,0,0);
INSERT INTO "dishes" VALUES(14,2,'Картофель фри с пармезаном',350,NULL,NULL,0,1,0,0);
INSERT INTO "dishes" VALUES(15,2,'Поп-корн из креветок',590,NULL,NULL,0,0,0,0);
INSERT INTO "dishes" VALUES(16,8,'Оливье в провансальском маринаде',250,NULL,NULL,0,0,0,0);
INSERT INTO "dishes" VALUES(17,8,'Тартар из говядины с картофельными чипсами',700,NULL,NULL,0,0,1,0);
INSERT INTO "dishes" VALUES(18,8,'Хумус из печёного перца с роти',400,NULL,NULL,0,1,0,0);
INSERT INTO "dishes" VALUES(19,7,'Бородинский',120,NULL,NULL,0,1,0,0);
INSERT INTO "dishes" VALUES(20,7,'Льняной',120,NULL,NULL,0,1,0,0);
INSERT INTO "dishes" VALUES(21,7,'Роти',90,NULL,NULL,0,1,0,0);
INSERT INTO "dishes" VALUES(22,5,'Соус на выбор',90,NULL,NULL,0,1,0,0);
INSERT INTO "dishes" VALUES(23,1,'Бургер с томлёной уткой',550,NULL,NULL,0,0,0,0);
INSERT INTO "dishes" VALUES(24,1,'Смеш-бургер',790,NULL,NULL,0,0,0,0);
INSERT INTO "dishes" VALUES(25,1,'Томлёные щёчки с пюре из сельдерея',980,NULL,NULL,0,0,0,0);
INSERT INTO "dishes" VALUES(26,1,'Индейка с печёными овощами и томатной сальсой',670,NULL,NULL,0,0,0,1);
INSERT INTO "dishes" VALUES(27,1,'Судак под двумя соусами с брокколи',650,NULL,NULL,0,0,0,1);
INSERT INTO "dishes" VALUES(28,1,'Филе миньон со шпинатом',1200,NULL,NULL,0,0,0,0);
CREATE TABLE drinks (
                id INTEGER PRIMARY KEY,
                category_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                price INTEGER,
                volume_ml INTEGER,
                composition TEXT,
                description TEXT,
                is_non_alcoholic BOOLEAN DEFAULT 0,
                is_vegetarian BOOLEAN DEFAULT 0,
                is_new BOOLEAN DEFAULT 0,
                is_healthy BOOLEAN DEFAULT 0,
                FOREIGN KEY (category_id) REFERENCES categories(id)
            );
INSERT INTO "drinks" VALUES(1,11,'Clausthaler б/а',300,330,NULL,NULL,1,0,0,0);
INSERT INTO "drinks" VALUES(2,10,'Клубника — красный базилик',390,NULL,NULL,NULL,0,1,0,0);
INSERT INTO "drinks" VALUES(3,10,'Манго-маракуйя-алоэ',390,NULL,NULL,NULL,0,1,0,0);
INSERT INTO "drinks" VALUES(4,10,'Яблоко-ваниль-лемонграсс',390,NULL,NULL,NULL,0,1,0,0);
INSERT INTO "drinks" VALUES(5,11,'Coca-Cola',250,NULL,NULL,NULL,0,0,0,0);
INSERT INTO "drinks" VALUES(6,11,'Вода Magura (газ/негаз)',250,NULL,NULL,NULL,0,0,0,0);
INSERT INTO "drinks" VALUES(7,11,'Глинтвейн б/а',350,NULL,NULL,NULL,0,0,0,0);
INSERT INTO "drinks" VALUES(8,11,'Какао',300,NULL,NULL,NULL,0,0,0,0);
INSERT INTO "drinks" VALUES(9,11,'Мандариновый пунш б/а',350,NULL,NULL,NULL,0,0,0,0);
INSERT INTO "drinks" VALUES(10,11,'Матча',400,NULL,NULL,NULL,0,0,0,1);
INSERT INTO "drinks" VALUES(11,11,'Матча-кокос',450,NULL,NULL,NULL,0,0,0,1);
INSERT INTO "drinks" VALUES(12,11,'Сок Il Primo',250,NULL,NULL,NULL,0,0,0,0);
INSERT INTO "drinks" VALUES(13,11,'Фреш',350,NULL,NULL,NULL,0,1,0,0);
INSERT INTO "drinks" VALUES(14,9,'Американо',200,NULL,NULL,NULL,0,0,0,0);
INSERT INTO "drinks" VALUES(15,9,'Горячий Бамбл красный апельсин',400,NULL,NULL,NULL,0,0,0,0);
INSERT INTO "drinks" VALUES(16,9,'Капучино',300,NULL,NULL,NULL,0,0,0,0);
INSERT INTO "drinks" VALUES(17,9,'Латте',300,NULL,NULL,NULL,0,0,0,0);
INSERT INTO "drinks" VALUES(18,9,'Раф',370,NULL,NULL,NULL,0,0,0,0);
INSERT INTO "drinks" VALUES(19,9,'Раф халва',400,NULL,NULL,NULL,0,0,0,0);
INSERT INTO "drinks" VALUES(20,9,'Флэт уайт',300,NULL,NULL,NULL,0,0,0,0);
INSERT INTO "drinks" VALUES(21,9,'Эспрессо',200,NULL,NULL,NULL,0,0,0,0);
INSERT INTO "drinks" VALUES(22,9,'Эспрессо-тоник гранат-розмарин',300,NULL,NULL,NULL,0,0,1,0);
INSERT INTO "drinks" VALUES(23,12,'Иван-чай фермерский',450,NULL,NULL,NULL,0,0,0,0);
INSERT INTO "drinks" VALUES(24,12,'Клубника-ваниль',590,NULL,NULL,NULL,0,0,0,0);
INSERT INTO "drinks" VALUES(25,12,'Облепиха-груша',590,NULL,NULL,NULL,0,0,0,0);
INSERT INTO "drinks" VALUES(26,12,'Смородина-мята',590,NULL,NULL,NULL,0,0,0,0);
INSERT INTO "drinks" VALUES(27,12,'Чай листовой',450,NULL,NULL,NULL,0,0,0,0);
COMMIT;

-- Unified menu view
CREATE VIEW menu_full AS
SELECT
  'dish' as type,
  d.id,
  d.name,
  c.name as category,
  d.price,
  d.is_spicy,
  d.is_vegetarian,
  d.is_new,
  d.is_healthy,
  d.composition,
  d.description
FROM dishes d
JOIN categories c ON d.category_id = c.id
WHERE c.type = 'kitchen'
UNION ALL
SELECT
  'drink' as type,
  dr.id,
  dr.name,
  c.name as category,
  dr.price,
  0 as is_spicy,
  dr.is_vegetarian,
  dr.is_new,
  dr.is_healthy,
  dr.composition,
  dr.description
FROM drinks dr
JOIN categories c ON dr.category_id = c.id
WHERE c.type = 'bar';

COMMIT;