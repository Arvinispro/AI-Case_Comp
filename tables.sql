CREATE TABLE public.course_materials (
  id uuid NOT NULL,
  course_id uuid,
  material bytea,
  text_material text,
  is_text boolean,
  created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT course_materials_pkey PRIMARY KEY (id),
  CONSTRAINT course_materials_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id)
);
CREATE TABLE public.courses (
  id uuid NOT NULL,
  user_id uuid,
  name text NOT NULL,
  details text,
  created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT courses_pkey PRIMARY KEY (id),
  CONSTRAINT courses_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);
CREATE TABLE public.past_problems (
  id uuid NOT NULL,
  course_id uuid,
  question text,
  answer text,
  lllm_conversation bytea,
  created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT past_problems_pkey PRIMARY KEY (id),
  CONSTRAINT past_problems_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id)
);
CREATE TABLE public.users (
  id uuid NOT NULL,
  username text NOT NULL,
  xp integer,
  level integer,
  learning_type uuid,
  created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT users_pkey PRIMARY KEY (id)
);