--
-- PostgreSQL database dump
--

-- Dumped from database version 11.1
-- Dumped by pg_dump version 11.1

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
-- Name: check_req_flair_or_tag(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.check_req_flair_or_tag() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
--    NEW RECORD;
    req_flair BOOL;
    req_tag BOOL;
    sub_name VARCHAR;
    sub_flair_id VARCHAR;
BEGIN
--    SELECT * INTO NEW FROM submissions WHERE id = 16;

    IF NEW.flair_id IS NULL THEN
        SELECT subreddits.req_flair, flair_id, name INTO req_flair, sub_flair_id, sub_name FROM subreddits WHERE id = NEW.subreddit_id;
        IF req_flair AND sub_flair_id IS NULL THEN
            RAISE EXCEPTION '/r/% requires flair', sub_name USING detail = 
                format('subreddit_id=%s,submission_id=%s', NEW.subreddit_id, NEW.id), errcode = 'EB001';
        END IF;
    END IF;

    IF NEW.custom_tag IS NULL THEN
        SELECT subreddits.req_tag, name INTO req_tag, sub_name FROM subreddits WHERE id = NEW.subreddit_id;
        IF req_tag THEN
            RAISE EXCEPTION '/r/% requires a tag', sub_name USING detail = 
                format('subreddit_id=%s,submission_id=%s', NEW.subreddit_id, NEW.id), errcode = 'EB002';
        END IF;
    END IF;

    RETURN NEW;
END;
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
    SELECT last_submission_on INTO old_last_post FROM subreddits WHERE id = NEW.subreddit_id;

    IF old_last_post IS NULL OR old_last_post < NEW.submitted_on THEN
        UPDATE subreddits SET last_submission_on = NEW.submitted_on WHERE id = NEW.subreddit_id;
    END IF;

    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_with_oids = false;

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
    flair_id character varying
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
    name character varying,
    tag_series boolean DEFAULT false NOT NULL,
    flair_id character varying,
    rehost boolean DEFAULT true,
    last_submission_on timestamp without time zone,
    req_flair boolean DEFAULT false NOT NULL,
    req_tag boolean DEFAULT false NOT NULL
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
    artist character varying NOT NULL,
    title character varying NOT NULL,
    series character varying,
    nsfw boolean DEFAULT false NOT NULL,
    source_url character varying NOT NULL,
    source_image_url character varying NOT NULL,
    imgur_id character varying,
    imgur_image_url character varying
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
-- Name: submissions submissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT submissions_pkey PRIMARY KEY (id);


--
-- Name: submissions submissions_work_id_subreddit_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT submissions_work_id_subreddit_id_key UNIQUE (work_id, subreddit_id);


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
-- Name: works works_source_url_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.works
    ADD CONSTRAINT works_source_url_key UNIQUE (source_url);


--
-- Name: submissions check_req_flair_or_tag; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER check_req_flair_or_tag AFTER INSERT OR UPDATE ON public.submissions FOR EACH ROW EXECUTE PROCEDURE public.check_req_flair_or_tag();


--
-- Name: submissions update_last_submission_on; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER update_last_submission_on AFTER INSERT OR UPDATE OF submitted_on ON public.submissions FOR EACH ROW EXECUTE PROCEDURE public.update_last_submission_on();


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

