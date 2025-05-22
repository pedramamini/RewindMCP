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

    # use a time range from last week (increased time range)
    now = datetime.datetime.now()
    last_week = now - datetime.timedelta(days=7)
    from_time = last_week.replace(hour=9, minute=0, second=0).isoformat()
    to_time = now.isoformat()

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


def test_search(base_url, keyword="meeting", relative="7days"):
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


def test_get_screenshot(base_url, frame_id=1):
    """test the get_screenshot tool.

    args:
        base_url: base url of the mcp server
        frame_id: id of the screenshot frame to retrieve
    """

    print(f"\ntesting get_screenshot with frame_id={frame_id}")

    url = f"{base_url}/mcp/tools/get_screenshot"
    payload = {"frame_id": frame_id}

    response = requests.post(url, json=payload)

    if response.status_code == 200:
        data = response.json()
        screenshot = data.get("screenshot")
        if screenshot:
            print("success! retrieved screenshot")
            print(f"time: {screenshot.get('time')}")
            print(f"application: {screenshot.get('application')}")
            print(f"window: {screenshot.get('window')}")
            print(f"has image data: {'yes' if screenshot.get('image_data') else 'no'}")

            # If image data exists, extract and print the path from the data URL
            if screenshot.get('image_data'):
                # Data URLs are in format: data:image/jpeg;base64,BASE64_DATA
                # We can't extract the original path, but we can show it's available
                print(f"image format: {screenshot.get('image_data').split(';')[0].split(':')[1]}")
        else:
            print("success, but no screenshot data returned")
    else:
        print(f"error: {response.status_code}")
        print(response.text)


def test_get_screenshots_relative(base_url, time_period="1day", limit=5):
    """test the get_screenshots_relative tool.

    args:
        base_url: base url of the mcp server
        time_period: relative time period to query
        limit: maximum number of screenshots to return
    """

    print(f"\ntesting get_screenshots_relative with time_period={time_period}, limit={limit}")

    url = f"{base_url}/mcp/tools/get_screenshots_relative"
    payload = {"time_period": time_period, "limit": limit}

    response = requests.post(url, json=payload)

    if response.status_code == 200:
        data = response.json()
        screenshots = data.get("screenshots", [])
        print(f"success! found {len(screenshots)} screenshots")

        # print a sample of the first screenshot if available
        if screenshots:
            print("\nsample screenshot:")
            print(f"time: {screenshots[0]['time']}")
            print(f"application: {screenshots[0]['application']}")
            print(f"window: {screenshots[0]['window']}")
            print(f"has image data: {'yes' if screenshots[0].get('image_data') else 'no'}")

            # If image data exists, extract and print the path from the data URL
            if screenshots[0].get('image_data'):
                # Data URLs are in format: data:image/jpeg;base64,BASE64_DATA
                # We can't extract the original path, but we can show it's available
                print(f"image format: {screenshots[0].get('image_data').split(';')[0].split(':')[1]}")
    else:
        print(f"error: {response.status_code}")
        print(response.text)


def test_get_screenshots_absolute(base_url):
    """test the get_screenshots_absolute tool.

    args:
        base_url: base url of the mcp server
    """

    print("\ntesting get_screenshots_absolute")

    # use a time range from last week
    now = datetime.datetime.now()
    last_week = now - datetime.timedelta(days=7)
    from_time = last_week.replace(hour=9, minute=0, second=0).isoformat()
    to_time = now.isoformat()

    print(f"time range: {from_time} to {to_time}")

    url = f"{base_url}/mcp/tools/get_screenshots_absolute"
    payload = {"from": from_time, "to": to_time, "limit": 5}

    response = requests.post(url, json=payload)

    if response.status_code == 200:
        data = response.json()
        screenshots = data.get("screenshots", [])
        print(f"success! found {len(screenshots)} screenshots")

        # print a sample of the first screenshot if available
        if screenshots:
            print("\nsample screenshot:")
            print(f"time: {screenshots[0]['time']}")
            print(f"application: {screenshots[0]['application']}")
            print(f"window: {screenshots[0]['window']}")
            print(f"has image data: {'yes' if screenshots[0].get('image_data') else 'no'}")

            # If image data exists, extract and print the path from the data URL
            if screenshots[0].get('image_data'):
                # Data URLs are in format: data:image/jpeg;base64,BASE64_DATA
                # We can't extract the original path, but we can show it's available
                print(f"image format: {screenshots[0].get('image_data').split(';')[0].split(':')[1]}")
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
    parser.add_argument("--time-period", default="7days", help="relative time period for transcript retrieval")
    parser.add_argument("--frame-id", type=int, default=1, help="frame id for screenshot retrieval")

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

    # test get_screenshot
    test_get_screenshot(base_url, args.frame_id)

    # test get_screenshots_relative
    test_get_screenshots_relative(base_url, args.time_period)

    # test get_screenshots_absolute
    test_get_screenshots_absolute(base_url)

    print("\nall tests completed")


if __name__ == "__main__":
    main()