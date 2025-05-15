#!/usr/bin/env python
"""
test_mcp_server.py - test script for the rewinddb mcp server.

this script demonstrates how to interact with the mcp server
by making requests to the available tools.
"""

import json
import requests
import datetime
import argparse


def test_get_transcripts_relative(base_url, time_period="1hour"):
    """test the get_transcripts_relative tool.

    args:
        base_url: base url of the mcp server
        time_period: relative time period to query
    """

    print(f"\ntesting get_transcripts_relative with time_period={time_period}")

    url = f"{base_url}/mcp/tools/get_transcripts_relative"
    payload = {"time_period": time_period}

    response = requests.post(url, json=payload)

    if response.status_code == 200:
        data = response.json()
        transcripts = data.get("transcripts", [])
        print(f"success! found {len(transcripts)} transcript sessions")

        # print a sample of the first transcript if available
        if transcripts:
            print("\nsample transcript:")
            print(f"time: {transcripts[0]['start_time']}")
            print(f"text: {transcripts[0]['text'][:100]}...")
    else:
        print(f"error: {response.status_code}")
        print(response.text)


def test_get_transcripts_absolute(base_url):
    """test the get_transcripts_absolute tool.

    args:
        base_url: base url of the mcp server
    """

    print("\ntesting get_transcripts_absolute")

    # use a time range from yesterday
    now = datetime.datetime.now()
    yesterday = now - datetime.timedelta(days=1)
    from_time = yesterday.replace(hour=9, minute=0, second=0).isoformat()
    to_time = yesterday.replace(hour=17, minute=0, second=0).isoformat()

    print(f"time range: {from_time} to {to_time}")

    url = f"{base_url}/mcp/tools/get_transcripts_absolute"
    payload = {"from": from_time, "to": to_time}

    response = requests.post(url, json=payload)

    if response.status_code == 200:
        data = response.json()
        transcripts = data.get("transcripts", [])
        print(f"success! found {len(transcripts)} transcript sessions")

        # print a sample of the first transcript if available
        if transcripts:
            print("\nsample transcript:")
            print(f"time: {transcripts[0]['start_time']}")
            print(f"text: {transcripts[0]['text'][:100]}...")
    else:
        print(f"error: {response.status_code}")
        print(response.text)


def test_search(base_url, keyword="meeting", relative="1day"):
    """test the search tool.

    args:
        base_url: base url of the mcp server
        keyword: keyword to search for
        relative: relative time period to search in
    """

    print(f"\ntesting search with keyword='{keyword}', relative='{relative}'")

    url = f"{base_url}/mcp/tools/search"
    payload = {"keyword": keyword, "relative": relative}

    response = requests.post(url, json=payload)

    if response.status_code == 200:
        data = response.json()
        audio_results = data.get("audio", [])
        screen_results = data.get("screen", [])

        print(f"success! found {len(audio_results)} audio matches and {len(screen_results)} screen matches")

        # print a sample of the first audio result if available
        if audio_results:
            print("\nsample audio match:")
            print(f"time: {audio_results[0]['time']}")
            print(f"text: {audio_results[0]['text']}")

        # print a sample of the first screen result if available
        if screen_results:
            print("\nsample screen match:")
            print(f"time: {screen_results[0]['time']}")
            print(f"application: {screen_results[0]['application']}")
            print(f"text: {screen_results[0]['text'][:100]}...")
    else:
        print(f"error: {response.status_code}")
        print(response.text)


def test_list_tools(base_url):
    """test the list tools endpoint.

    args:
        base_url: base url of the mcp server
    """

    print("\ntesting list tools")

    url = f"{base_url}/mcp/tools"

    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        tools = data.get("tools", [])
        print(f"success! found {len(tools)} tools")

        for tool in tools:
            print(f"- {tool['name']}: {tool['description']}")
    else:
        print(f"error: {response.status_code}")
        print(response.text)


def test_health(base_url):
    """test the health check endpoint.

    args:
        base_url: base url of the mcp server
    """

    print("\ntesting health check")

    url = f"{base_url}/health"

    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        print(f"success! server status: {data.get('status')}")
    else:
        print(f"error: {response.status_code}")
        print(response.text)


def parse_arguments():
    """parse command line arguments.

    returns:
        parsed argument namespace
    """

    parser = argparse.ArgumentParser(
        description="test script for the rewinddb mcp server"
    )

    parser.add_argument("--host", default="localhost", help="mcp server host")
    parser.add_argument("--port", type=int, default=8000, help="mcp server port")
    parser.add_argument("--keyword", default="meeting", help="keyword to search for")
    parser.add_argument("--time-period", default="1hour", help="relative time period for transcript retrieval")

    return parser.parse_args()


def main():
    """main entry point."""

    args = parse_arguments()

    base_url = f"http://{args.host}:{args.port}"
    print(f"testing mcp server at {base_url}")

    # test health check
    test_health(base_url)

    # test list tools
    test_list_tools(base_url)

    # test get_transcripts_relative
    test_get_transcripts_relative(base_url, args.time_period)

    # test get_transcripts_absolute
    test_get_transcripts_absolute(base_url)

    # test search
    test_search(base_url, args.keyword)

    print("\nall tests completed")


if __name__ == "__main__":
    main()