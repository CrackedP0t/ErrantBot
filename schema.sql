--
-- PostgreSQL database dump
--

-- Dumped from database version 11.2
-- Dumped by pg_dump version 11.2

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: artist_not_alias(integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.artist_not_alias(artist_id integer) RETURNS boolean
    LANGUAGE sql
    AS $$
    SELECT alias_of is null from artists where id = artist_id;
$$;


--
-- Name: check_require_flair(character varying, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.check_require_flair(new_flair_id character varying, subreddit_id integer) RETURNS boolean
    LANGUAGE sql
    AS $$
    SELECT new_flair_id IS NOT NULL OR NOT (SELECT require_flair FROM subreddits WHERE id = subreddit_id AND flair_id IS NULL);
$$;


--
-- Name: check_require_series(integer, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.check_require_series(work_id integer, subreddit_id integer) RETURNS boolean
    LANGUAGE sql
    AS $$
    SELECT EXISTS(SELECT FROM subreddits WHERE id = subreddit_id AND NOT require_series) OR EXISTS(SELECT FROM works WHERE id = work_id AND series IS NOT NULL);
$$;


--
-- Name: check_require_tag(integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.check_require_tag(artist_id integer) RETURNS boolean
    LANGUAGE sql
    AS $$
    SELECT alias_of is not null from artists where id = artist_id;
$$;


--
-- Name: check_require_tag(character varying, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.check_require_tag(new_custom_tag character varying, subreddit_id integer) RETURNS boolean
    LANGUAGE sql
    AS $$
    SELECT new_custom_tag IS NOT NULL OR NOT (SELECT require_tag FROM subreddits WHERE id = subreddit_id);
$$;


--
-- Name: update_last_submission_on(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_last_submission_on() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    old_last_post TIMESTAMP;
BEGIN
    UPDATE subreddits SET last_submission_on = 
        (SELECT submitted_on FROM submissions WHERE subreddit_id = NEW.subreddit_id ORDER BY submitted_on DESC NULLS LAST LIMIT 1)
        WHERE id = NEW.subreddit_id;

    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_with_oids = false;

--
-- Name: artists; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.artists (
    id integer NOT NULL,
    name character varying NOT NULL,
    alias_of integer,
    CONSTRAINT artists_not_reflexive CHECK ((id <> alias_of))
);


--
-- Name: artists_id_seq1; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.artists_id_seq1
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: artists_id_seq1; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.artists_id_seq1 OWNED BY public.artists.id;


--
-- Name: submissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.submissions (
    id integer NOT NULL,
    work_id integer NOT NULL,
    subreddit_id integer NOT NULL,
    reddit_id character varying,
    custom_tag character varying,
    submitted_on timestamp without time zone,
    flair_id character varying,
    CONSTRAINT check_require_flair CHECK (public.check_require_flair(flair_id, subreddit_id)),
    CONSTRAINT check_require_series CHECK (public.check_require_series(work_id, subreddit_id)),
    CONSTRAINT check_require_tag CHECK (public.check_require_tag(custom_tag, subreddit_id))
);


--
-- Name: submissions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.submissions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: submissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.submissions_id_seq OWNED BY public.submissions.id;


--
-- Name: subreddits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.subreddits (
    id integer NOT NULL,
    name character varying NOT NULL,
    tag_series boolean DEFAULT false NOT NULL,
    flair_id character varying,
    last_submission_on timestamp without time zone,
    require_flair boolean DEFAULT false NOT NULL,
    require_tag boolean DEFAULT false NOT NULL,
    space_out boolean DEFAULT true NOT NULL,
    require_series boolean DEFAULT false NOT NULL,
    disabled boolean DEFAULT false NOT NULL,
    sfw_only boolean DEFAULT false NOT NULL
);


--
-- Name: subreddits_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.subreddits_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: subreddits_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.subreddits_id_seq OWNED BY public.subreddits.id;


--
-- Name: works; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.works (
    id integer NOT NULL,
    title character varying NOT NULL,
    series character varying,
    nsfw boolean DEFAULT false NOT NULL,
    source_url character varying NOT NULL,
    source_image_url character varying,
    imgur_id character varying,
    imgur_url character varying,
    source_image_urls character varying[],
    is_album boolean DEFAULT false NOT NULL,
    artist_id integer NOT NULL,
    CONSTRAINT check_artist_not_alias CHECK (public.artist_not_alias(artist_id)),
    CONSTRAINT multiple_or_one CHECK ((((source_image_urls IS NOT NULL) AND (source_image_url IS NULL)) OR ((source_image_urls IS NULL) AND (source_image_url IS NOT NULL))))
);


--
-- Name: works_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.works_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: works_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.works_id_seq OWNED BY public.works.id;


--
-- Name: artists id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artists ALTER COLUMN id SET DEFAULT nextval('public.artists_id_seq1'::regclass);


--
-- Name: submissions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.submissions ALTER COLUMN id SET DEFAULT nextval('public.submissions_id_seq'::regclass);


--
-- Name: subreddits id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subreddits ALTER COLUMN id SET DEFAULT nextval('public.subreddits_id_seq'::regclass);


--
-- Name: works id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.works ALTER COLUMN id SET DEFAULT nextval('public.works_id_seq'::regclass);


--
-- Name: submissions already_exists; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT already_exists UNIQUE (work_id, subreddit_id);


--
-- Name: artists artists_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artists
    ADD CONSTRAINT artists_name_key UNIQUE (name);


--
-- Name: artists artists_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artists
    ADD CONSTRAINT artists_pkey PRIMARY KEY (id);


--
-- Name: submissions submissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT submissions_pkey PRIMARY KEY (id);


--
-- Name: subreddits subreddits_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subreddits
    ADD CONSTRAINT subreddits_name_key UNIQUE (name);


--
-- Name: subreddits subreddits_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subreddits
    ADD CONSTRAINT subreddits_pkey PRIMARY KEY (id);


--
-- Name: works works_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.works
    ADD CONSTRAINT works_pkey PRIMARY KEY (id);


--
-- Name: works works_source_image_url_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.works
    ADD CONSTRAINT works_source_image_url_key UNIQUE (source_image_url);


--
-- Name: submissions update_last_submission_on; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_last_submission_on AFTER INSERT OR DELETE OR UPDATE OF submitted_on ON public.submissions FOR EACH ROW EXECUTE PROCEDURE public.update_last_submission_on();


--
-- Name: artists artists_alias_of_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artists
    ADD CONSTRAINT artists_alias_of_fkey FOREIGN KEY (alias_of) REFERENCES public.artists(id);


--
-- Name: submissions submissions_subreddit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT submissions_subreddit_id_fkey FOREIGN KEY (subreddit_id) REFERENCES public.subreddits(id);


--
-- Name: submissions submissions_work_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT submissions_work_id_fkey FOREIGN KEY (work_id) REFERENCES public.works(id);


--
-- PostgreSQL database dump complete
--

